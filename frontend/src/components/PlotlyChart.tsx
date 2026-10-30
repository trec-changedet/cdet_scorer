import { useEffect, useRef } from "react";

declare global {
  interface Window {
    Plotly?: {
      react: (
        el: HTMLElement,
        data: unknown[],
        layout: Record<string, unknown>,
        config?: Record<string, unknown>
      ) => void;
      purge: (el: HTMLElement) => void;
    };
  }
}

interface PlotlyChartProps {
  data: unknown[];
  layout: Record<string, unknown>;
  className?: string;
  onPointClick?: (point: { x: unknown; y: unknown; text?: string }) => void;
}

export function PlotlyChart({ data, layout, className, onPointClick }: PlotlyChartProps) {
  const containerRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = containerRef.current as (HTMLDivElement & {
      on?: (event: string, cb: (ev: { points?: { x: unknown; y: unknown; text?: string }[] }) => void) => void;
      removeAllListeners?: (event: string) => void;
    }) | null;

    if (!el || !window.Plotly) return;

    window.Plotly.react(el, data, layout, {
      responsive: true,
      displayModeBar: false,
    });

    if (onPointClick && el.on) {
      el.removeAllListeners?.("plotly_click");
      el.on("plotly_click", (ev) => {
        if (ev.points && ev.points[0]) {
          onPointClick(ev.points[0]);
        }
      });
    }
  }, [data, layout, onPointClick]);

  useEffect(() => {
    const el = containerRef.current;
    return () => {
      if (el && window.Plotly) {
        window.Plotly.purge(el);
      }
    };
  }, []);

  return <div ref={containerRef} className={className ?? "w-full min-h-[360px]"} />;
}
