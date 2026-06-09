interface Props {
  backendStatus?: string;
}

export function ConvertTopBar({ backendStatus }: Props) {
  const backendOnline = (backendStatus || '').includes('0.3.0');

  return (
    <div className="topbar">
      <div className="brand">
        <div className="logo">CV</div>
        <div>
          <div className="title">SQL Dialect Convert</div>
          <div className="sub">Hive / Spark / StarRocks conversion workbench</div>
        </div>
      </div>
      <div className="actions">
        <span className="pill trusted">Convert Page</span>
        <div className="status-indicator" title="Backend Service">
          <span className="status-label">Backend</span>
          <span className={`dot ${backendOnline ? 'online' : 'offline'}`}></span>
        </div>
      </div>
    </div>
  );
}
