import { useEffect, useMemo, useState } from 'react';
import { apiUrl, fluxClass } from './api';
import { DynamicSpectrum } from './components/DynamicSpectrum';
import { GoesChart } from './components/GoesChart';
import { LightCurve } from './components/LightCurve';
import { useDashboardData } from './useDashboardData';

function useUtcClock() {
  const [now, setNow] = useState(new Date());
  useEffect(() => {
    const timer = window.setInterval(() => setNow(new Date()), 1000);
    return () => window.clearInterval(timer);
  }, []);
  return now;
}

function formatUtc(date: Date | null, includeDate = false) {
  if (!date) return 'Awaiting data';
  return new Intl.DateTimeFormat('en-GB', {
    ...(includeDate && { day: '2-digit', month: 'short', year: 'numeric' }),
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: false,
    timeZone: 'UTC',
    timeZoneName: 'short',
  }).format(date);
}

function PanelHeader({
  eyebrow,
  title,
  meta,
}: {
  eyebrow: string;
  title: string;
  meta?: string;
}) {
  return (
    <div className="panel-header">
      <div>
        <p className="eyebrow">{eyebrow}</p>
        <h2>{title}</h2>
      </div>
      {meta && <span className="panel-meta">{meta}</span>}
    </div>
  );
}

function App() {
  const now = useUtcClock();
  const {
    frames,
    lightCurve,
    goes,
    goesImageRefreshToken,
    events,
    health,
    lastFrameAt,
    frameCount,
    error,
  } = useDashboardData();
  const currentGoesClass = fluxClass(goes?.current_flux ?? null);
  const peakGoesClass = fluxClass(goes?.peak_flux ?? null);
  const currentPower = lightCurve.at(-1);
  const typeThreeCount = useMemo(
    () =>
      events?.detections.filter((event) =>
        (event.class ?? '').toLowerCase().includes('iii'),
      ).length ?? 0,
    [events],
  );
  const isLive = health?.live_spectrum || frames.length > 0;

  return (
    <div className="app-shell">
      <header className="topbar">
        <a className="brand" href={import.meta.env.BASE_URL} aria-label="OVRO-LWA dashboard home">
          <span className="brand-mark" aria-hidden="true">
            <span />
            <span />
            <span />
          </span>
          <span className="brand-copy">
            <strong>OVRO–LWA</strong>
            <small>Solar Monitor</small>
          </span>
        </a>
        <div className="header-status">
          <span className={`live-pill ${isLive ? 'online' : 'offline'}`}>
            <i /> {isLive ? 'Live' : 'Connecting'}
          </span>
          <span className="utc-clock">{formatUtc(now, true)}</span>
        </div>
      </header>

      <main>
        <section className="intro-row">
          <div>
            <p className="section-kicker">Owens Valley Radio Observatory</p>
            <p className="intro-copy">
              Real-time low-frequency radio observations paired with operational
              space-weather measurements.
            </p>
          </div>
          <div className="source-tags" aria-label="Data sources">
            <span>OVRO–LWA</span>
            <span>NOAA GOES-{goes?.satellite ?? '—'}</span>
          </div>
        </section>

        <section className="metric-grid" aria-label="Current activity summary">
          <article className="metric-card accent-yellow">
            <p>Last 24 hours</p>
            <div className="metric-main">
              <strong>{peakGoesClass}</strong>
              <span>Peak GOES class</span>
            </div>
            <small>1–8 Å soft X-ray flux</small>
          </article>
          <article className="metric-card accent-cyan">
            <p>Right now</p>
            <div className="metric-main">
              <strong>{currentGoesClass}</strong>
              <span>GOES X-ray class</span>
            </div>
            <small>{goes?.updated ? `Updated ${formatUtc(new Date(goes.updated))}` : 'Loading NOAA feed'}</small>
          </article>
          <article className="metric-card accent-orange">
            <p>Radio bursts</p>
            <div className="metric-main">
              <strong>{typeThreeCount}</strong>
              <span>Type III now</span>
            </div>
            <small>{events ? `${events.count} total current detections` : 'Detection feed loading'}</small>
          </article>
          <article className="metric-card accent-green">
            <p>Array status</p>
            <div className="metric-main status-main">
              <strong>{isLive ? 'ONLINE' : 'WAIT'}</strong>
              <span>Live stream</span>
            </div>
            <small>{error ?? `${frames.length} frames in view`}</small>
          </article>
        </section>

        <section className="dashboard-grid">
          <div className="primary-column">
            <article className="panel spectrum-panel">
              <PanelHeader
                eyebrow="OVRO–LWA · STOKES I"
                title="Live Dynamic Spectrum"
                meta={`15–85 MHz · ${formatUtc(lastFrameAt)}`}
              />
              <DynamicSpectrum frames={frames} />
              <div className="panel-footer">
                <span><i className="status-dot" /> 512 ms cadence</span>
                <span>{frameCount.toLocaleString()} frames received this session</span>
                <span>Window: 300 s</span>
              </div>
            </article>

            <article className="panel lightcurve-panel">
              <PanelHeader
                eyebrow="MIDDLE CHANNEL"
                title="Live Light Curve"
                meta="50.0 MHz · Relative power (dB)"
              />
              <LightCurve values={lightCurve} />
              <div className="panel-footer">
                <span><i className="status-dot cyan" /> Channel 384 / 768</span>
                <span>Current: {currentPower ? `${currentPower.toFixed(1)} dB` : '—'}</span>
              </div>
            </article>

            <article className="panel goes-panel">
              <PanelHeader
                eyebrow="NOAA SPACE WEATHER"
                title="GOES X-Ray Flux"
                meta={`Primary satellite GOES-${goes?.satellite ?? '—'} · Last 300 s`}
              />
              <div className="legend">
                <span><i className="legend-line short" /> 0.5–4 Å</span>
                <span><i className="legend-line long" /> 1–8 Å</span>
              </div>
              <GoesChart points={goes?.points ?? []} />
              <div className="panel-footer">
                <span>Source: NOAA SWPC</span>
                <span>Current class: <b>{currentGoesClass}</b> · Refresh: 10 s</span>
              </div>
            </article>
          </div>

          <aside className="side-column">
            <article className="panel image-panel placeholder-panel">
              <PanelHeader eyebrow="OVRO–LWA IMAGING" title="Live Solar Image" meta="Reserved" />
              <div className="image-placeholder" role="img" aria-label="Placeholder for future live OVRO-LWA solar image">
                <div className="placeholder-grid" />
                <div className="solar-orbit"><span /></div>
                <svg viewBox="0 0 64 64" aria-hidden="true">
                  <path d="M12 51h40M32 51V31M21 31a11 11 0 0 0 22 0M18 18l14 13 14-13" />
                </svg>
                <strong>Imaging feed reserved</strong>
                <p>The panel is ready for the live OVRO–LWA image pipeline.</p>
                <span className="coming-soon">Coming soon</span>
              </div>
            </article>

            <article className="panel image-panel goes-image-panel">
              <PanelHeader eyebrow="GOES / SUVI · 195 Å" title="Latest Solar Image" meta="Near real time" />
              <div className="goes-image-wrap">
                <img
                  src={`${apiUrl('/api/goes/image')}?v=${goesImageRefreshToken}`}
                  alt="Latest GOES SUVI 195 angstrom image of the Sun"
                />
                <div className="image-crosshair horizontal" />
                <div className="image-crosshair vertical" />
                <span className="image-live-badge"><i /> NOAA LIVE</span>
              </div>
              <div className="panel-footer">
                <span>Extreme ultraviolet</span>
                <span>Refresh: 5 min</span>
              </div>
            </article>

            <article className="panel about-panel">
              <p className="eyebrow">ABOUT THE DATA</p>
              <p>
                The Long Wavelength Array watches the radio Sun from Owens Valley,
                California. GOES context is clipped from NOAA’s public real-time feed.
              </p>
              <a href="https://www.ovro.caltech.edu/research/ovro-lwa" target="_blank" rel="noreferrer">
                About OVRO–LWA <span>↗</span>
              </a>
            </article>
          </aside>
        </section>
      </main>

      <footer>
        <span>OVRO–LWA Solar Monitor</span>
        <span>Data are preliminary and intended for monitoring.</span>
      </footer>
    </div>
  );
}

export default App;
