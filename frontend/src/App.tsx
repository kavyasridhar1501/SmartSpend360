import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import Layout from './components/Layout'
import Dashboard from './pages/Dashboard'
import Transactions from './pages/Transactions'
import Anomalies from './pages/Anomalies'
import Forecast from './pages/Forecast'
import Alerts from './pages/Alerts'
import Pipeline from './pages/Pipeline'

export default function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Navigate to="/dashboard" replace />} />
          <Route path="dashboard" element={<Dashboard />} />
          <Route path="transactions" element={<Transactions />} />
          <Route path="anomalies" element={<Anomalies />} />
          <Route path="forecast" element={<Forecast />} />
          <Route path="alerts" element={<Alerts />} />
          <Route path="pipeline" element={<Pipeline />} />
        </Route>
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </BrowserRouter>
  )
}
