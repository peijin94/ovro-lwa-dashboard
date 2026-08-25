import { useEffect, useRef } from 'react';
import type { SpectrumFrame } from '../api';

interface DynamicSpectrumProps {
  frames: SpectrumFrame[];
}

const FREQ_MIN = 15;
const FREQ_MAX = 85;

function colorMap(value: number): [number, number, number] {
  const t = Math.max(0, Math.min(1, value));
  const stops: Array<[number, number, number]> = [
    [4, 7, 28],
    [30, 42, 116],
    [25, 113, 155],
    [43, 174, 128],
    [193, 220, 69],
    [255, 219, 91],
  ];
  const scaled = t * (stops.length - 1);
  const index = Math.min(stops.length - 2, Math.floor(scaled));
  const mix = scaled - index;
  const a = stops[index];
  const b = stops[index + 1];
  return [
    Math.round(a[0] + (b[0] - a[0]) * mix),
    Math.round(a[1] + (b[1] - a[1]) * mix),
    Math.round(a[2] + (b[2] - a[2]) * mix),
  ];
}

export function DynamicSpectrum({ frames }: DynamicSpectrumProps) {
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
      const width = Math.max(1, Math.floor(rect.width * dpr));
      const height = Math.max(1, Math.floor(rect.height * dpr));
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      context.fillStyle = '#080b12';
      context.fillRect(0, 0, width, height);
      const left = 62 * dpr;
      const right = 18 * dpr;
      const top = 18 * dpr;
      const bottom = 34 * dpr;
      const plotW = width - left - right;
      const plotH = height - top - bottom;

      context.strokeStyle = '#202634';
      context.lineWidth = dpr;
      context.font = `${10 * dpr}px ui-monospace, SFMono-Regular, monospace`;
      context.fillStyle = '#7f8ba3';
      context.textAlign = 'right';
      context.textBaseline = 'middle';
      [15, 25, 35, 45, 55, 65, 75, 85].forEach((frequency) => {
        const y = top + ((FREQ_MAX - frequency) / (FREQ_MAX - FREQ_MIN)) * plotH;
        context.beginPath();
        context.moveTo(left, y);
        context.lineTo(left + plotW, y);
        context.stroke();
        context.fillText(`${frequency} MHz`, left - 8 * dpr, y);
      });

      context.textAlign = 'center';
      context.textBaseline = 'top';
      ['−300s', '−225s', '−150s', '−75s', 'Now'].forEach((label, index) => {
        const x = left + (index / 4) * plotW;
        context.beginPath();
        context.moveTo(x, top);
        context.lineTo(x, top + plotH);
        context.stroke();
        context.fillText(label, x, top + plotH + 10 * dpr);
      });

      if (!frames.length) return;
      const bins = frames[0].length;
      const texture = document.createElement('canvas');
      texture.width = Math.max(frames.length, 1);
      texture.height = bins;
      const textureContext = texture.getContext('2d');
      if (!textureContext) return;
      const image = textureContext.createImageData(texture.width, texture.height);

      frames.forEach((frame, x) => {
        frame.forEach((raw, bin) => {
          const normalized = (Math.log10(Math.max(raw, 1e4)) - 4) / 4;
          const [red, green, blue] = colorMap(normalized);
          const y = bins - 1 - bin;
          const offset = (y * texture.width + x) * 4;
          image.data[offset] = red;
          image.data[offset + 1] = green;
          image.data[offset + 2] = blue;
          image.data[offset + 3] = 255;
        });
      });
      textureContext.putImageData(image, 0, 0);
      context.imageSmoothingEnabled = true;
      context.drawImage(texture, left, top, plotW, plotH);
    }

    draw(canvas, context);
    const observer = new ResizeObserver(() => draw(canvas, context));
    observer.observe(canvas);
    return () => observer.disconnect();
  }, [frames]);

  return (
    <canvas
      ref={canvasRef}
      className="chart-canvas spectrum-canvas"
      aria-label="Live OVRO-LWA dynamic spectrum from 15 to 85 megahertz"
    />
  );
}
