import type { ButtonHTMLAttributes } from "react";
import buttonStyles from "../components/cyberui/button.module.css";

export { Button } from "../components/cyberui/button";
export { Input } from "../components/cyberui/input";
export { Select } from "../components/cyberui/select";
export { Slider } from "../components/cyberui/slider";
export { Textarea } from "../components/cyberui/textarea";
export { Progress } from "../components/cyberui/progress";

export function HoldButton({ children, className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button {...props} className={`${buttonStyles.button} ${className}`} data-size="md" data-corners="tr-bl"
      data-variant={className.includes("stop") ? "danger" : "secondary"}>
      <span aria-hidden="true" data-slot="decoration" className={buttonStyles.shape} />
      {children}
    </button>
  );
}
