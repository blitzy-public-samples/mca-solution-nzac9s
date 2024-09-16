import React, { useState, useEffect } from 'react';
import { getApplications } from '@/services/api';
import { ApplicationListItem } from '@/components/ApplicationListItem';
import { formatDate, formatCurrency } from '@/utils/formatters';

// HUMAN ASSISTANCE NEEDED
// The following component may need additional refinement for production readiness.
// Please review and adjust as necessary.

const ApplicationList: React.FC = () => {
  const [applications, setApplications] = useState([]);
  const [sortColumn, setSortColumn] = useState('');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('asc');
  const [filter, setFilter] = useState('');
  const [currentPage, setCurrentPage] = useState(1);
  const [totalPages, setTotalPages] = useState(1);

  useEffect(() => {
    fetchApplications();
  }, [currentPage, sortColumn, sortDirection, filter]);

  const fetchApplications = async () => {
    try {
      const response = await getApplications({
        page: currentPage,
        sortBy: sortColumn,
        sortDirection,
        filter,
      });
      setApplications(response.data);
      setTotalPages(response.totalPages);
    } catch (error) {
      console.error('Error fetching applications:', error);
    }
  };

  const handleSort = (column: string) => {
    if (column === sortColumn) {
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      setSortColumn(column);
      setSortDirection('asc');
    }
  };

  const handleFilter = (event: React.ChangeEvent<HTMLInputElement>) => {
    setFilter(event.target.value);
    setCurrentPage(1);
  };

  const renderSortIcon = (column: string) => {
    if (column !== sortColumn) return null;
    return sortDirection === 'asc' ? '▲' : '▼';
  };

  return (
    <div className="application-list">
      <input
        type="text"
        placeholder="Filter applications..."
        value={filter}
        onChange={handleFilter}
      />
      <table>
        <thead>
          <tr>
            <th onClick={() => handleSort('businessName')}>
              Business Name {renderSortIcon('businessName')}
            </th>
            <th onClick={() => handleSort('requestedAmount')}>
              Requested Amount {renderSortIcon('requestedAmount')}
            </th>
            <th onClick={() => handleSort('submissionDate')}>
              Submission Date {renderSortIcon('submissionDate')}
            </th>
            <th>Status</th>
            <th>Actions</th>
          </tr>
        </thead>
        <tbody>
          {applications.map((application) => (
            <ApplicationListItem
              key={application.id}
              application={application}
              formatDate={formatDate}
              formatCurrency={formatCurrency}
            />
          ))}
        </tbody>
      </table>
      <div className="pagination">
        <button
          onClick={() => setCurrentPage(currentPage - 1)}
          disabled={currentPage === 1}
        >
          Previous
        </button>
        <span>
          Page {currentPage} of {totalPages}
        </span>
        <button
          onClick={() => setCurrentPage(currentPage + 1)}
          disabled={currentPage === totalPages}
        >
          Next
        </button>
      </div>
    </div>
  );
};

export default ApplicationList;