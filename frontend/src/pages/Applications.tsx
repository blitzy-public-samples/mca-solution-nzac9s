import React, { useState, useEffect } from 'react';
import ApplicationList from '@/components/ApplicationList';
import ApplicationDetail from '@/components/ApplicationDetail';
import { getApplications } from '@/services/api';

const Applications: React.FC = () => {
  const [applications, setApplications] = useState([]);
  const [selectedApplication, setSelectedApplication] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetchApplications();
  }, [currentPage, filter]);

  const fetchApplications = async () => {
    try {
      const response = await getApplications(currentPage, filter);
      setApplications(response.data);
    } catch (error) {
      console.error('Error fetching applications:', error);
    }
  };

  const handleApplicationSelect = (application) => {
    setSelectedApplication(application);
  };

  const handlePageChange = (page) => {
    setCurrentPage(page);
  };

  const handleFilterChange = (newFilter) => {
    setFilter(newFilter);
    setCurrentPage(1);
  };

  return (
    <div className="applications-page">
      <h1>MCA Applications</h1>
      <div className="applications-container">
        <ApplicationList
          applications={applications}
          onSelectApplication={handleApplicationSelect}
          currentPage={currentPage}
          onPageChange={handlePageChange}
          filter={filter}
          onFilterChange={handleFilterChange}
        />
        {selectedApplication && (
          <ApplicationDetail application={selectedApplication} />
        )}
      </div>
    </div>
  );
};

export default Applications;

// HUMAN ASSISTANCE NEEDED
// The following aspects may need further implementation or refinement:
// 1. Error handling and displaying error messages to the user
// 2. Loading states while fetching applications
// 3. Proper typing for the application data and state
// 4. Implementing more advanced filtering options if required
// 5. Handling cases where no applications are available