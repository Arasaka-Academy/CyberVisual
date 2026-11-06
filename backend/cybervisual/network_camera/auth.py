import base64
import hashlib
import hmac
import os
import threading
import time
from collections import OrderedDict

from werkzeug.http import parse_dict_header

from .soap import NS, parse_utc


class DeviceCredentials(object):
    realm = "CyberVisual"

    def __init__(self, username="", password=""):
        self.username = username
        self._password = password
        self._secret = os.urandom(32)
        self._lock = threading.Lock()
        self._seen = OrderedDict()

    @classmethod
    def from_environment(cls):
        return cls(os.environ.get("CYBERVISUAL_ONVIF_USERNAME", ""),
                   os.environ.get("CYBERVISUAL_ONVIF_PASSWORD", ""))

    @property
    def configured(self):
        return bool(self.username and self._password)

    def configure_rtsp_auth(self, auth, token):
        # Keep the password private to the authentication boundary.
        auth.add_digest(self.username, self._password, token)

    def verify_wsse(self, root):
        if not self.configured:
            return False
        tokens = root.findall(".//wsse:Security/wsse:UsernameToken", NS)
        if len(tokens) != 1:
            return False
        token = tokens[0]
        user = token.find("wsse:Username", NS)
        password = token.find("wsse:Password", NS)
        nonce = token.find("wsse:Nonce", NS)
        created = token.find("wsu:Created", NS)
        if any(item is None for item in (user, password, nonce, created)):
            return False
        if user.text != self.username or password.get("Type") != NS["wsse_password_digest"]:
            return False
        try:
            stamp = parse_utc(created.text)
            raw_nonce = base64.b64decode(nonce.text, validate=True)
            if not 8 <= len(raw_nonce) <= 256 or abs(time.time() - stamp) > 300:
                return False
            expected = base64.b64encode(hashlib.sha1(raw_nonce + created.text.encode() + self._password.encode()).digest()).decode()
            if not hmac.compare_digest(expected, password.text or ""):
                return False
        except (ValueError, TypeError, AttributeError):
            return False
        # Different Base64 padding bits can represent the same nonce bytes.
        return self._remember(("wsse", raw_nonce, created.text), 1)

    def challenge(self):
        stamp = str(int(time.time()))
        value = stamp + ":" + hmac.new(self._secret, stamp.encode(), hashlib.sha256).hexdigest()
        nonce = base64.b64encode(value.encode()).decode()
        return 'Digest realm="%s", nonce="%s", algorithm=MD5, qop="auth"' % (self.realm, nonce)

    def verify_digest(self, method, uri, authorization):
        if not self.configured or not authorization or not authorization.startswith("Digest "):
            return False
        values = parse_dict_header(authorization[7:])
        if values.get("username") != self.username or values.get("realm") != self.realm:
            return False
        if values.get("uri") != uri or values.get("qop") != "auth" or values.get("algorithm", "MD5").upper() != "MD5":
            return False
        try:
            nonce = values["nonce"]
            stamp, signature = base64.b64decode(nonce, validate=True).decode().split(":", 1)
            expected = hmac.new(self._secret, stamp.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(expected, signature) or not 0 <= time.time() - int(stamp) <= 300:
                return False
            nc, cnonce = values["nc"], values["cnonce"]
            if len(nc) != 8 or int(nc, 16) <= 0 or not cnonce or len(cnonce) > 256:
                return False
            md5 = lambda value: hashlib.md5(value.encode()).hexdigest()
            ha1 = md5("%s:%s:%s" % (self.username, self.realm, self._password))
            ha2 = md5("%s:%s" % (method, uri))
            expected = md5("%s:%s:%s:%s:auth:%s" % (ha1, nonce, nc, cnonce, ha2))
            if not hmac.compare_digest(expected, values.get("response", "")):
                return False
        except (KeyError, ValueError, TypeError, UnicodeError):
            return False
        return self._remember(("digest", nonce, cnonce), int(nc, 16))

    def _remember(self, key, sequence):
        with self._lock:
            now = time.monotonic()
            while self._seen and next(iter(self._seen.values()))[1] < now - 600:
                self._seen.popitem(last=False)
            previous = self._seen.get(key)
            if previous and sequence <= previous[0]:
                return False
            # Reject new sessions at capacity; do not evict valid replay protection.
            if previous is None and len(self._seen) >= 8192:
                return False
            self._seen[key] = (sequence, now)
            self._seen.move_to_end(key)
            return True
