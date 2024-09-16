import React from 'react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import Layout from '@/components/Layout';
import Home from '@/pages/Home';
import Applications from '@/pages/Applications';
import Webhooks from '@/pages/Webhooks';
import Settings from '@/pages/Settings';
import Admin from '@/pages/Admin';
import { AuthProvider } from '@/services/auth';

const App: React.FC = () => {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Layout>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/applications" element={<Applications />} />
            <Route path="/webhooks" element={<Webhooks />} />
            <Route path="/settings" element={<Settings />} />
            <Route path="/admin" element={<Admin />} />
          </Routes>
        </Layout>
      </BrowserRouter>
    </AuthProvider>
  );
};

export default App;

// HUMAN ASSISTANCE NEEDED
// The current implementation does not include protected routes for authenticated users only.
// Consider implementing a ProtectedRoute component or using a higher-order component to wrap
// routes that should only be accessible to authenticated users. This may involve checking the
// authentication state from the AuthProvider and redirecting unauthenticated users to a login page.