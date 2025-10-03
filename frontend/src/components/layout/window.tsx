import { useState, useRef } from "react";
import { cn } from "@/lib/utils";
import { TextParticle, type TextParticleProps } from "../ui/text-particle";
import { useDrag } from "@/hooks/use-drag";
import { Square, Minus, Copy, X } from "lucide-react";

const TEXT_PARTICLE_THROTTLE = 400;
const TEXT_PARTICLE_REMOVE_DELAY = 800;

function randomAngle(minAngle: number, maxAngle: number) {
  return Math.round((Math.random() * (maxAngle - minAngle) + minAngle) * 100) / 100;
}

type WindowLayoutProps = {
  title?: string;
  initialPosition?: { x: number; y: number };
  position?: { x: number; y: number };
  setPosition?: (position: { x: number; y: number }) => void;
  onClose?: () => void;
  onMinimize?: () => void;
  onMaximize?: () => void;
} & React.ComponentProps<"div">;

function WindowLayout({
  className,
  initialPosition,
  position: externalPosition,
  setPosition: externalSetPosition,
  children,
  title = "Window",
  onClose,
  onMinimize,
  onMaximize,
  style,
  ...props
}: WindowLayoutProps) {
  const windowRef = useRef<HTMLDivElement>(null);
  const draggableHeaderRef = useRef<HTMLDivElement>(null);

  const [textParticleProps, setTextParticleProps] = useState<TextParticleProps[]>([]);
  const lastClickCreatedAt = useRef<number>(0);

  const [maximized, setMaximized] = useState(false);

  const { position, isDragging } = useDrag({
    initialPosition,
    position: externalPosition,
    setPosition: externalSetPosition,
    ref: windowRef,
    dragHandleRef: draggableHeaderRef,
    style,
  });

  const createClickAnimation = (e: React.MouseEvent) => {
    const now = Date.now();

    if (now - lastClickCreatedAt.current < TEXT_PARTICLE_THROTTLE) {
      return;
    }

    lastClickCreatedAt.current = now;
    const id = now.toString();
    const angle = randomAngle(-30, 30);

    setTextParticleProps((prev) => [
      ...prev,
      {
        x: e.clientX,
        y: e.clientY,
        angle,
        id,
        text: "Click!",
      },
    ]);

    setTimeout(() => {
      setTextParticleProps((prev) => prev.filter((animation) => animation.id !== id));
    }, TEXT_PARTICLE_REMOVE_DELAY);
  };

  const handleIconClick = (e: React.MouseEvent, action?: () => void) => {
    e.stopPropagation();
    e.preventDefault();

    createClickAnimation(e);

    if (action) {
      // TODO:  I am not a fun of that. It might make our app
      //        feel sluggish.
      setTimeout(() => action(), 150);
    }
  };

  return (
    <>
      <div
        ref={windowRef}
        data-slot="window"
        className={cn(
          "fixed rounded-base border-2 border-border bg-background text-foreground font-base shadow-shadow min-w-[300px] min-h-[200px] flex flex-col",
          isDragging && "select-none",
          className
        )}
        style={{
          ...style,
          left: position.x,
          top: position.y,
          zIndex: 40,
        }}
        {...props}>
        {/* Header Bar */}
        <div
          ref={draggableHeaderRef}
          data-slot="window-header"
          className={cn(
            "flex items-center justify-between px-4 py-2 bg-main text-main-foreground border-b-2 border-border rounded-t-[3px] select-none",
            "font-heading"
          )}>
          <div className="flex-1 truncate">{title}</div>

          {/* Header Icons */}
          <div className="flex gap-1 ml-2">
            {/* Minimize */}
            <button
              onClick={(e) => {
                setMaximized(false);
                handleIconClick(e, onMinimize);
              }}
              className="window-button"
              aria-label="Minimize">
              <span className="text-xs font-bold">
                <Minus />
              </span>
            </button>

            {/* Maximize & minimize */}
            <button
              onClick={(e) => {
                if (!maximized) {
                  handleIconClick(e, onMaximize);
                } else {
                  handleIconClick(e, onMinimize);
                }
                setMaximized(!maximized);
              }}
              className="window-button"
              aria-label="Maximize">
              <span className="text-xs font-bold flex items-center justify-center">
                {!maximized ? (
                  <Copy transform="scale(-1,1)" size={"60%"} />
                ) : (
                  <Square size={"70%"} />
                )}
              </span>
            </button>

            {/* Close */}
            <button
              onClick={(e) => handleIconClick(e, onClose)}
              className="window-button"
              aria-label="Close">
              <X />
            </button>
          </div>
        </div>

        {/* Window Body */}
        {children}
      </div>

      {/* Click Animations */}
      {textParticleProps.map((anim) => (
        <TextParticle key={anim.id} {...anim} />
      ))}
    </>
  );
}

function WindowHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="window-content-header"
      className={cn(
        "grid auto-rows-min grid-rows-[auto_auto] items-start gap-1.5 has-[data-slot=window-action]:grid-cols-[1fr_auto] mb-4",
        className
      )}
      {...props}
    />
  );
}

function WindowTitle({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="window-title"
      className={cn("font-heading leading-none text-lg", className)}
      {...props}
    />
  );
}

function WindowDescription({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="window-description" className={cn("text-sm font-base", className)} {...props} />
  );
}

function WindowAction({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="window-action"
      className={cn("col-start-2 row-span-2 row-start-1 self-start justify-self-end", className)}
      {...props}
    />
  );
}

function WindowContent({ className, ...props }: React.ComponentProps<"div">) {
  return <div data-slot="window-content" className={cn("relative", className)} {...props} />;
}

function WindowBody({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div data-slot="window-body" className={cn("flex-1 p-6 overflow-auto", className)} {...props} />
  );
}

function WindowFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="window-footer"
      className={cn("flex items-center mt-4 pt-4 border-t-2 border-border", className)}
      {...props}
    />
  );
}

export {
  WindowLayout as Window,
  WindowHeader,
  WindowTitle,
  WindowDescription,
  WindowContent,
  WindowBody,
  WindowAction,
  WindowFooter,
};
