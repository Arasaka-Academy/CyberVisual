import time

from .events import TOPICS
from .onvif_device import service_capabilities
from .soap import NS, SOAPFault, add, duration, node, parse_utc, q, text, utc


CONCRETE_SET = "http://www.onvif.org/ver10/tev/topicExpression/ConcreteSet"
CONCRETE = "http://docs.oasis-open.org/wsn/t-1/TopicExpression/Concrete"


def _lifetime(value):
    return duration(value, 60) if value is None or value.startswith("P") else parse_utc(value) - time.time()


def _filter(request):
    expression_filter = request.find("tev:Filter", NS)
    if expression_filter is None:
        return None
    expressions = list(expression_filter)
    if len(expressions) != 1 or expressions[0].tag != q("wsnt:TopicExpression"):
        raise SOAPFault("ter:InvalidFilter", "Only topic expression filters are supported.")
    expression = expressions[0]
    if expression.get("Dialect") not in (CONCRETE_SET, CONCRETE):
        raise SOAPFault("ter:InvalidFilter", "Unsupported topic expression dialect.")
    topics = []
    for value in (expression.text or "").split("|"):
        path = value.strip()
        path = path.split(":", 1)[-1]
        if path not in TOPICS:
            raise SOAPFault("ter:InvalidFilter", "Unsupported topic expression.")
        topics.append(path)
    return topics


def _notification(response, event):
    notification = add(response, "wsnt:NotificationMessage")
    add(notification, "wsnt:Topic", "cv:" + event["topic"], Dialect=CONCRETE)
    message = add(add(notification, "wsnt:Message"), "tt:Message", UtcTime=utc(event["frame_ts"]),
                  PropertyOperation="Initialized" if event["initialized"] else "Changed")
    add(add(message, "tt:Source"), "tt:SimpleItem", Name="VideoSourceToken", Value=event["source"])
    data = add(message, "tt:Data")
    add(data, "tt:SimpleItem", Name="Category", Value=event["category"])
    add(data, "tt:SimpleItem", Name="State", Value="true" if event["state"] else "false")
    if event.get("id"):
        add(data, "tt:SimpleItem", Name="EventId", Value=event["id"])
    if event.get("gap"):
        add(data, "tt:SimpleItem", Name="Gap", Value="true")


def events_request(server, operation, request, subscription=None):
    broker = server.runtime.events
    prefix = "wsnt" if operation in ("Renew", "Unsubscribe") else "tev"
    response = node(prefix + ":" + operation + "Response")
    if operation == "GetServiceCapabilities":
        response.append(service_capabilities("tev"))
    elif operation == "GetEventProperties":
        add(response, "tev:TopicNamespaceLocation", NS["cv"])
        add(response, "tev:FixedTopicSet", "true")
        topic_set = add(response, "wstop:TopicSet")
        branches = {}
        for topic in TOPICS:
            branch_name, leaf_name = topic.split("/")
            if branch_name not in branches:
                branches[branch_name] = add(topic_set, "cv:" + branch_name)
            leaf = add(branches[branch_name], "cv:" + leaf_name)
            leaf.set(q("wstop:topic"), "true")
            description = add(leaf, "tt:MessageDescription", IsProperty="true")
            add(add(description, "tt:Source"), "tt:SimpleItemDescription", Name="VideoSourceToken", Type="tt:ReferenceToken")
            data = add(description, "tt:Data")
            add(data, "tt:SimpleItemDescription", Name="Category", Type="xs:string")
            add(data, "tt:SimpleItemDescription", Name="State", Type="xs:boolean")
        add(response, "tev:TopicExpressionDialect", CONCRETE_SET)
        add(response, "tev:TopicExpressionDialect", CONCRETE)
        add(response, "tev:MessageContentSchemaLocation", "http://www.onvif.org/ver10/schema/onvif.xsd")
    elif operation == "CreatePullPointSubscription":
        item = broker.subscribe(_lifetime(text(request, "tev:InitialTerminationTime")), _filter(request))
        reference = add(response, "tev:SubscriptionReference")
        add(reference, "wsa:Address", server.http_url("/onvif/subscriptions/" + item["id"]))
        add(response, "wsnt:CurrentTime", utc())
        add(response, "wsnt:TerminationTime", utc(item["expires"]))
    elif operation in ("PullMessages", "Renew", "Unsubscribe", "SetSynchronizationPoint"):
        if not subscription:
            raise SOAPFault("ter:InvalidArgVal", "Use the subscription's returned endpoint address.")
        if operation == "PullMessages":
            timeout = duration(text(request, "tev:Timeout"), 0)
            limit = int(text(request, "tev:MessageLimit", "64"))
            messages = broker.pull(subscription, timeout=timeout, limit=limit)
            add(response, "tev:CurrentTime", utc())
            add(response, "tev:TerminationTime", utc(broker.expiry(subscription)))
            for event in messages:
                _notification(response, event)
        elif operation == "Renew":
            expiry = broker.renew(subscription, _lifetime(text(request, "wsnt:TerminationTime")))
            add(response, "wsnt:TerminationTime", utc(expiry))
            add(response, "wsnt:CurrentTime", utc())
        elif operation == "Unsubscribe":
            broker.unsubscribe(subscription)
        else:
            broker.synchronize(subscription)
    else:
        raise SOAPFault("ter:ActionNotSupported", "Event operation is not supported.")
    return response
