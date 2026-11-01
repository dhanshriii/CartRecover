import { useCallback, useEffect, useMemo, useState } from 'react'
import './App.css'

const n = v => Number(v ?? 0).toLocaleString('en-IN')
const money = p => new Intl.NumberFormat('en-IN', { style: 'currency', currency: 'INR', maximumFractionDigits: 2 }).format(Number(p ?? 0) / 100)

function Metric({ label, value, note, symbol, accent = '' }) {
  return <article className={`metric ${accent}`}><div className="metric-head"><span>{label}</span><b>{symbol}</b></div><strong>{value}</strong><small>{note}</small></article>
}
function Panel({ title, sub, children, className = '' }) {
  return <section className={`panel ${className}`}><div className="panel-head"><div><h2>{title}</h2><p>{sub}</p></div></div>{children}</section>
}
function Result({ item }) {
  if (!item || (!item.result && !item.error)) return null
  return <div className={`result ${item.error ? 'bad' : 'good'}`}><b>{item.error ? 'Request failed' : 'API response'}</b><pre>{item.error || JSON.stringify(item.result, null, 2)}</pre></div>
}

export default function App() {
  const [data, setData] = useState(null), [loading, setLoading] = useState(true)
  const [apiError, setApiError] = useState(''), [updated, setUpdated] = useState(null)
  const [cartId, setCartId] = useState(''), [channel, setChannel] = useState('EMAIL')
  const [sendId, setSendId] = useState(`DASH-${Date.now()}`)
  const [orderId, setOrderId] = useState(''), [attributionId, setAttributionId] = useState(`ATTR-DASH-${Date.now()}`)
  const [busy, setBusy] = useState(''), [results, setResults] = useState({})

  const refresh = useCallback(async () => {
    setLoading(true); setApiError('')
    try {
      const r = await fetch('/api/analytics/overview')
      if (!r.ok) throw new Error(`Analytics API returned HTTP ${r.status}`)
      setData(await r.json()); setUpdated(new Date())
    } catch (e) { setApiError(`${e.message}. Check that FastAPI is running on port 8000.`) }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])

  async function post(key, path, payload) {
    setBusy(key); setResults(x => ({ ...x, [key]: null }))
    try {
      const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const body = await r.json().catch(() => ({}))
      if (!r.ok) throw new Error(typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail ?? body))
      setResults(x => ({ ...x, [key]: { result: body } }))
      await refresh()
    } catch (e) { setResults(x => ({ ...x, [key]: { error: e.message } })) }
    finally { setBusy('') }
  }

  const m = data?.messaging ?? {}, c = data?.carts ?? {}, o = data?.orders ?? {}
  const reasons = useMemo(() => Object.entries(m.suppression_reasons ?? {}).sort((a,b) => b[1]-a[1]), [data])
  const totalReasons = reasons.reduce((s, x) => s + Number(x[1]), 0)
  const totalAttempts = Number(m.total_attempts || 0)
  const cartReady = !!cartId.trim()

  return <div className="shell">
    <aside className="sidebar">
      <div className="brand"><div className="logo">CR</div><div><b>CartRecover</b><small>COMMERCE INTELLIGENCE</small></div></div>
      <div className="nav-caption">WORKSPACE</div>
      <a className="nav active" href="#overview">▦ &nbsp; Overview</a>
      <a className="nav" href="#campaigns">◉ &nbsp; Campaign operations</a>
      <a className="nav" href="#actions">⌁ &nbsp; Recovery actions</a>
      <a className="nav" href="#attribution">↗ &nbsp; Attribution</a>
      <div className="side-foot"><span className="green-dot"/> API workspace <small>CartRecover · v1.0.0</small></div>
    </aside>
    <main className="main">
      <header className="topbar"><span>Workspace <i>/</i> Overview</span><div><label className="live"><i/> LIVE DATA</label><button className="secondary" onClick={refresh} disabled={loading}>{loading ? 'Refreshing…' : '↻ Refresh'}</button></div></header>
      <div className="content" id="overview">
        <div className="title-row"><div><label className="eyebrow">OPERATIONS OVERVIEW</label><h1>Recovery performance</h1><p>Monitor abandoned carts, campaign execution and attributed outcomes.</p></div><small className="updated">{updated ? `Updated ${updated.toLocaleTimeString()}` : 'Connecting to API…'}</small></div>
        {apiError && <div className="alert">{apiError}</div>}
        <div className="section-label">BUSINESS SNAPSHOT <span/></div>
        <div className="metrics">
          <Metric label="Total customers" value={n(data?.customers?.total)} note="Customer records" symbol="♙"/>
          <Metric label="Abandoned carts" value={n(c.currently_abandoned)} note={`${n(c.total)} total carts`} symbol="▤"/>
          <Metric label="Recovered carts" value={n(c.recovered)} note={`${Number(c.recovery_rate_percent ?? 0).toFixed(2)}% snapshot recovery rate`} symbol="✓" accent="green"/>
          <Metric label="Attributed revenue" value={money(o.attributed_revenue_paise)} note={`${n(o.attributed_orders)} attributed orders`} symbol="₹" accent="purple"/>
        </div>
        <div className="two-col" id="campaigns">
          <Panel title="Messaging performance" sub="Send-attempt statuses recorded in the database">
            <div className="total-row"><div><small>TOTAL SEND ATTEMPTS</small><strong>{n(m.total_attempts)}</strong></div><span className="sent-tag">● {n(m.sent)} sent</span></div>
            <div className="bar"><i className="sent" style={{width:`${100*(m.sent||0)/(totalAttempts||1)}%`}}/><i className="scheduled" style={{width:`${100*(m.scheduled||0)/(totalAttempts||1)}%`}}/><i className="suppressed" style={{width:`${100*(m.suppressed||0)/(totalAttempts||1)}%`}}/><i className="failed" style={{width:`${100*(m.failed||0)/(totalAttempts||1)}%`}}/></div>
            <div className="legend">
              {[['Sent',m.sent,'sent'],['Scheduled',m.scheduled,'scheduled'],['Suppressed',m.suppressed,'suppressed'],['Failed',m.failed,'failed']].map(([label,value,cls])=><div key={label}><i className={cls}/>{label}<b>{n(value)}</b></div>)}
            </div>
            <div className="engagement"><div><small>Delivered events</small><b>{n(m.delivery_events)}</b></div><div><small>Open events</small><b>{n(m.open_events)}</b></div><div><small>Click events</small><b>{n(m.click_events)}</b></div></div>
          </Panel>
          <Panel title="Suppression analysis" sub="Why recovery messages were blocked">
            {reasons.length ? <div className="reasons">{reasons.map(([reason,count])=><div key={reason}><div className="reason-top"><span>{reason.replaceAll('_',' ')}</span><b>{n(count)}</b></div><div className="track"><i style={{width:`${100*count/(totalReasons||1)}%`}}/></div><small>{(100*count/(totalReasons||1)).toFixed(1)}% of suppressed attempts</small></div>)}</div> : <p className="muted">{loading ? 'Loading…' : 'No suppression data returned.'}</p>}
          </Panel>
        </div>
        <div className="two-col lower">
          <Panel title="Conversion & revenue" sub="Order outcomes linked to recovery attribution">
            <div className="revenue"><div><small>ATTRIBUTED REVENUE</small><strong>{money(o.attributed_revenue_paise)}</strong></div><b>₹</b></div>
            <div className="order-stats"><div><small>Completed orders</small><b>{n(o.completed)}</b></div><div><small>Attributed orders</small><b>{n(o.attributed_orders)}</b></div><div><small>Attributed order share</small><b>{Number(o.attributed_order_rate_percent ?? 0).toFixed(2)}%</b></div><div><small>Purchased carts</small><b>{n(c.purchased)}</b></div></div>
            <p className="fine">Attributed revenue is campaign-linked revenue, not proof of incremental revenue caused by a campaign.</p>
          </Panel>
          <Panel title="Measurement notes" sub="Interpret the metrics correctly">
            <ul className="notes">{(data?.measurement_notes ?? ['Analytics notes will appear when the API responds.']).map((x,i)=><li key={i}>{x}</li>)}</ul>
          </Panel>
        </div>
        <div className="section-label spaced" id="actions">LIVE API OPERATIONS <span/></div>
        <div className="two-col actions">
          <Panel title="Evaluate recovery eligibility" sub="Check whether a cart can receive a recovery message">
            <form onSubmit={e=>{e.preventDefault();post('evaluate','/api/recovery/evaluate',{cart_id:cartId.trim(),channel})}}>
              <label>Cart ID<input required value={cartId} onChange={e=>setCartId(e.target.value)} placeholder="e.g. CART-2026-000001"/></label>
              <label>Channel<select value={channel} onChange={e=>setChannel(e.target.value)}><option value="EMAIL">Email</option><option value="SMS">SMS</option></select></label>
              <button className="primary" disabled={!cartReady || busy==='evaluate'}>{busy==='evaluate'?'Evaluating…':'Evaluate cart →'}</button>
            </form><Result item={results.evaluate}/>
          </Panel>
          <Panel title="Schedule recovery campaign" sub="Submit a scheduling request for a cart">
            <form onSubmit={e=>{e.preventDefault();post('schedule','/api/campaigns/schedule',{cart_id:cartId.trim(),channel,send_id:sendId.trim()})}}>
              <label>Cart ID<input required value={cartId} onChange={e=>setCartId(e.target.value)} placeholder="e.g. CART-2026-000001"/></label>
              <label>Channel<select value={channel} onChange={e=>setChannel(e.target.value)}><option value="EMAIL">Email</option><option value="SMS">SMS</option></select></label>
              <label>Send ID<input required value={sendId} onChange={e=>setSendId(e.target.value)}/></label>
              <button className="primary" disabled={!cartReady || !sendId.trim() || busy==='schedule'}>{busy==='schedule'?'Scheduling…':'Schedule campaign →'}</button>
            </form><Result item={results.schedule}/>
          </Panel>
          <Panel title="Record order attribution" sub="Attribute a completed order to a recovery interaction" className="wide" >
            <form onSubmit={e=>{e.preventDefault();post('attribute','/api/attribution',{order_id:orderId.trim(),attribution_id:attributionId.trim()})}}>
              <label>Order ID<input required value={orderId} onChange={e=>setOrderId(e.target.value)} placeholder="e.g. ORD-2026-000001"/></label>
              <label>Attribution ID<input required value={attributionId} onChange={e=>setAttributionId(e.target.value)}/></label>
              <button className="primary" disabled={!orderId.trim() || !attributionId.trim() || busy==='attribute'}>{busy==='attribute'?'Recording…':'Record attribution →'}</button>
            </form><Result item={results.attribute}/>
          </Panel>
        </div>
        <footer>CartRecover · Abandoned Cart Recovery & Conversion Attribution <span>FastAPI · SQLite</span></footer>
      </div>
    </main>
  </div>
}
