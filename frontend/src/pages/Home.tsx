import React from 'react';
import Dashboard from '@/components/Dashboard';
import ApplicationList from '@/components/ApplicationList';

const Home: React.FC = () => {
  return (
    <div className="home-container">
      <h1>Dashboard Overview</h1>
      <Dashboard />
      <h2>Recent Applications</h2>
      <ApplicationList recent={true} />
    </div>
  );
};

export default Home;