import { useEffect, useMemo, useState } from 'react';
import { apiUrl, fluxClass } from './api';
import { DynamicSpectrum } from './components/DynamicSpectrum';
import { GoesChart } from './components/GoesChart';
import { LightCurve } from './components/LightCurve';
import { shouldShowSunBanner, SUN_BANNER_ELEVATION_DEG } from './sun';
import { radioFluxAt } from './units';
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

function formatSfu(value: number | null) {
  if (value === null || !Number.isFinite(value)) return '—';
  if (value >= 100) return value.toFixed(0);
  if (value >= 10) return value.toFixed(1);
  return value.toFixed(2);
}

function formatProbability(probability: number | undefined) {
  if (probability === undefined || !Number.isFinite(probability)) return '—';
  return `${Math.round(probability * 100)}%`;
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
    flareNowcast,
    flareUpdatedAt,
    health,
    ephemeris,
    lastFrameAt,
    frameCount,
  } = useDashboardData();
  const currentGoesClass = fluxClass(goes?.current_flux ?? null);
  const peakGoesClass = fluxClass(goes?.peak_flux ?? null);
  const currentFlux = lightCurve.at(-1);
  const radioFlux40 = useMemo(
    () => frames.map((frame) => radioFluxAt(frame, 40)).filter((value) => value > 0),
    [frames],
  );
  const currentRadioFlux40 = radioFlux40.at(-1) ?? null;
  const peakRadioFlux40 = radioFlux40.length ? Math.max(...radioFlux40) : null;
  const isLive = health?.live_spectrum || frames.length > 0;
  const showSunBanner = shouldShowSunBanner(ephemeris?.elevation_deg ?? null);

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
            <small>Solar Radio Monitor</small>
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
        {showSunBanner && (
          <section className="sun-status-banner" role="status" aria-live="polite">
            <span className="sun-status-icon" aria-hidden="true">☼</span>
            <div>
              <strong>The Sun is not up yet for OVRO</strong>
              <small>
                Solar elevation {ephemeris?.elevation_deg.toFixed(1)}° · Banner clears at{' '}
                {SUN_BANNER_ELEVATION_DEG}°
              </small>
            </div>
          </section>
        )}
        <section className="metric-grid" aria-label="Current activity summary">
          <article className="metric-card accent-yellow">
            <p>40 MHz Radio Flux</p>
            <div className="metric-readouts">
              <div className="metric-readout">
                <strong>{formatSfu(peakRadioFlux40)} <em>s.f.u.</em></strong>
                <span><b>Peak</b> · Last 5 min</span>
              </div>
              <div className="metric-readout">
                <strong>{formatSfu(currentRadioFlux40)} <em>s.f.u.</em></strong>
                <span><b>Now</b></span>
              </div>
            </div>
            <small>{lastFrameAt ? `Updated ${formatUtc(lastFrameAt)}` : 'Waiting for radio stream'}</small>
          </article>
          <article className="metric-card accent-cyan">
            <p>X-Ray Flux · GOES X-Ray Class</p>
            <div className="metric-readouts">
              <div className="metric-readout">
                <strong>{peakGoesClass}</strong>
                <span><b>Peak</b> · Last 24 hrs</span>
              </div>
              <div className="metric-readout">
                <strong>{currentGoesClass}</strong>
                <span><b>Now</b></span>
              </div>
            </div>
            <small>{goes?.updated ? `Updated ${formatUtc(new Date(goes.updated))}` : 'Loading NOAA feed'}</small>
          </article>
          <article className="metric-card accent-orange nowcast-card">
            <p>Flare Nowcast</p>
            <div className="forecast-list">
              <div><strong>R1</strong><span><b>{formatProbability(flareNowcast?.['>M1']?.probability)}</b> &gt;M1 flare possibility</span></div>
              <div><strong>R2</strong><span><b>{formatProbability(flareNowcast?.['>M5']?.probability)}</b> &gt;M5 flare possibility</span></div>
              <div><strong>R3</strong><span><b>{formatProbability(flareNowcast?.['>X1']?.probability)}</b> &gt;X1 flare possibility</span></div>
            </div>
            <small>{flareUpdatedAt ? `Updated ${formatUtc(flareUpdatedAt)}` : 'Waiting for OVSA nowcast'}</small>
          </article>
          <article className="metric-card accent-green">
            <p>Radio Burst Detections</p>
            <div className="metric-main">
              <strong>0</strong>
              <span>bursts</span>
            </div>
            <small>Detection feed placeholder</small>
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
                meta="50.0 MHz · Flux density (s.f.u.) · Log scale"
              />
              <LightCurve values={lightCurve} />
              <div className="panel-footer">
                <span><i className="status-dot cyan" /> Channel 384 / 768</span>
                <span>Current: {currentFlux ? `${currentFlux.toFixed(2)} s.f.u.` : '—'}</span>
              </div>
            </article>

            <article className="panel goes-panel">
              <PanelHeader
                eyebrow="NOAA SPACE WEATHER"
                title="GOES X-Ray Flux"
                meta={`Primary satellite GOES-${goes?.satellite ?? '—'} · Last 30 min`}
              />
              <div className="legend">
                <span><i className="legend-line short" /> 0.5–4 Å</span>
                <span><i className="legend-line long" /> 1–8 Å</span>
              </div>
              <GoesChart points={goes?.points ?? []} />
              <div className="panel-footer">
                <span>Source: NOAA SWPC</span>
                <span>Current class: <b>{currentGoesClass}</b> · Refresh: 30 s</span>
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
        <span>OVRO–LWA Solar Radio Monitor</span>
        <span>Data are preliminary and intended for monitoring.</span>
      </footer>
    </div>
  );
}

export default App;
