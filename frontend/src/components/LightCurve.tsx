import { useEffect, useRef } from 'react';

interface LightCurveProps {
  values: number[];
}

function formatSfuTick(value: number): string {
  if (value >= 0.01 && value < 1_000) return value.toLocaleString('en-US');
  return value.toExponential(0);
}

export function LightCurve({ values }: LightCurveProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const context = canvas.getContext('2d');
    if (!context) return;

    function draw(
      canvas: HTMLCanvasElement,
      context: CanvasRenderingContext2D,
    ) {
      const rect = canvas.getBoundingClientRect();
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      canvas.width = Math.max(1, Math.floor(rect.width * dpr));
      canvas.height = Math.max(1, Math.floor(rect.height * dpr));
      const width = canvas.width;
      const height = canvas.height;
      const left = 50 * dpr;
      const right = 16 * dpr;
      const top = 16 * dpr;
      const bottom = 30 * dpr;
      const plotW = width - left - right;
      const plotH = height - top - bottom;

      context.clearRect(0, 0, width, height);
      context.font = `${9 * dpr}px ui-monospace, SFMono-Regular, monospace`;
      context.fillStyle = '#7f8ba3';
      context.strokeStyle = '#202634';
      context.lineWidth = dpr;

      const finite = values.filter((value) => Number.isFinite(value) && value > 0);
      const minValue = finite.length ? Math.min(...finite) : 1;
      const maxValue = finite.length ? Math.max(...finite) : 100;
      const minExponent = Math.floor(Math.log10(minValue));
      let maxExponent = Math.ceil(Math.log10(maxValue));
      if (maxExponent <= minExponent) maxExponent = minExponent + 1;
      const exponentSpan = maxExponent - minExponent;
      const tickStep = Math.max(1, Math.ceil(exponentSpan / 4));
      const tickExponents: number[] = [];
      for (
        let exponent = minExponent;
        exponent <= maxExponent;
        exponent += tickStep
      ) {
        tickExponents.push(exponent);
      }
      if (tickExponents.at(-1) !== maxExponent) tickExponents.push(maxExponent);

      context.textAlign = 'right';
      context.textBaseline = 'middle';
      tickExponents.forEach((exponent) => {
        const y = top + ((maxExponent - exponent) / exponentSpan) * plotH;
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillText(formatSfuTick(10 ** exponent), left - 8 * dpr, y);
      });

      context.textAlign = 'center';
      context.textBaseline = 'top';
      ['−300s', '−200s', '−100s', 'Now'].forEach((label, index) => {
        const x = left + (index / 3) * plotW;
        context.fillText(label, x, top + plotH + 9 * dpr);
      });

      if (values.length < 2) return;
      context.beginPath();
      let started = false;
      values.forEach((value, index) => {
        if (!Number.isFinite(value) || value <= 0) {
          started = false;
          return;
        }
        const x = left + (index / (values.length - 1)) * plotW;
        const logValue = Math.log10(value);
        const y = top + ((maxExponent - logValue) / exponentSpan) * plotH;
        if (!started) {
          context.moveTo(x, y);
          started = true;
        } else context.lineTo(x, y);
      });
      const gradient = context.createLinearGradient(left, 0, left + plotW, 0);
      gradient.addColorStop(0, '#2e8ca7');
      gradient.addColorStop(0.65, '#59d9f5');
      gradient.addColorStop(1, '#f4d35e');
      context.strokeStyle = gradient;
      context.lineWidth = 2 * dpr;
      context.stroke();
    }

    draw(canvas, context);
    const observer = new ResizeObserver(() => draw(canvas, context));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [values]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas lightcurve-canvas"
      aria-label="Live 50 megahertz light curve in solar flux units on a logarithmic scale for the last 300 seconds"
    />
  );
}
