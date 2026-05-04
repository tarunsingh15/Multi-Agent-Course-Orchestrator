import { useParams } from "react-router-dom";
import { useState, useEffect, useRef } from "react";
import './CourseStatusPage.css';

const API_BASE = 'https://profiles-api-536653873539.us-central1.run.app';

// Map backend statuses to user-friendly status categories
const getStatusCategory = (status) => {
  if (!status) return 'unknown';
  
  // Completed
  if (status === 'EVALUATION_COMPLETE') return 'completed';
  
  // Failed
  if (status === 'FAILED') return 'failed';
  
  // Running (actively processing)
  if (
    status === 'PROCESSING' ||
    status === 'PROCESSING_BLUEPRINT' ||
    status === 'PROCESSING_LESSON_EVAL' ||
    status === 'PROCESSING_LESSON_CRITIQUE' ||
    status === 'PROCESSING_REVISION' ||
    status === 'PROCESSING_QUIZ_GEN' ||
    status === 'PROCESSING_QUIZ_EVAL'
  ) return 'running';
  
  // Paused (waiting for user input or revision)
  if (status === 'REVISION_REQUESTED') return 'paused';
  
  // Queued (waiting to start)
  if (status === 'PENDING') return 'queued';
  
  // Running (intermediate states that indicate progress)
  return 'running';
};

// Get user-friendly status message
const getStatusMessage = (status) => {
  const statusMap = {
    'PENDING': 'Job is queued and waiting to start',
    'PROCESSING': 'Processing document...',
    'PARSING_COMPLETE': 'Document parsing completed',
    'PROCESSING_BLUEPRINT': 'Generating course blueprint...',
    'BLUEPRINT_COMPLETE': 'Blueprint generation completed',
    'REVISION_REQUESTED': 'Waiting for blueprint revision',
    'LESSON_GENERATED': 'Lessons generated',
    'PROCESSING_LESSON_EVAL': 'Evaluating lessons...',
    'LESSON_EVALUATED': 'Lesson evaluation completed',
    'PROCESSING_LESSON_CRITIQUE': 'Analyzing lessons and determining revision needs...',
    'PROCESSING_REVISION': 'Revising lessons...',
    'LESSON_CRITIQUE_COMPLETE': 'Lesson critique completed',
    'PROCESSING_QUIZ_GEN': 'Generating quizzes...',
    'QUIZ_GENERATED': 'Quizzes generated',
    'PROCESSING_QUIZ_EVAL': 'Evaluating quizzes...',
    'EVALUATION_COMPLETE': 'Course generation completed successfully!',
    'FAILED': 'Course generation failed'
  };
  
  return statusMap[status] || `Status: ${status}`;
};

export default function CourseStatusPage() {
  const { jobId } = useParams();
  const [jobData, setJobData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [isPolling, setIsPolling] = useState(true);
  const intervalRef = useRef(null);

  useEffect(() => {
    if (!jobId) {
      setError('No job ID provided');
      setLoading(false);
      return;
    }

    const fetchJobStatus = async () => {
      try {
        const res = await fetch(`${API_BASE}/jobs/${jobId}`);
        if (!res.ok) {
          throw new Error(`Failed to fetch job status: ${res.statusText}`);
        }
        const data = await res.json();
        setJobData(data);
        setError(null);
        
        // Stop polling if job is completed or failed
        const statusCategory = getStatusCategory(data.status);
        if (statusCategory === 'completed' || statusCategory === 'failed') {
          if (intervalRef.current) {
            clearInterval(intervalRef.current);
            intervalRef.current = null;
            setIsPolling(false);
          }
        } else {
          setIsPolling(true);
        }
      } catch (err) {
        console.error('Error fetching job status:', err);
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    // Initial fetch
    fetchJobStatus();

    // Poll every 3 seconds - continue polling until job is completed or failed
    intervalRef.current = setInterval(() => {
      fetchJobStatus();
    }, 3000);

    return () => {
      if (intervalRef.current) {
        clearInterval(intervalRef.current);
        intervalRef.current = null;
      }
    };
  }, [jobId]);

  if (loading) {
    return (
      <div className="status-page">
        <div className="status-container">
          <div className="loading">Loading job status...</div>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="status-page">
        <div className="status-container">
          <div className="error-message">Error: {error}</div>
        </div>
      </div>
    );
  }

  if (!jobData) {
    return (
      <div className="status-page">
        <div className="status-container">
          <div className="error-message">Job not found</div>
        </div>
      </div>
    );
  }

  const statusCategory = getStatusCategory(jobData.status);
  const statusMessage = getStatusMessage(jobData.status);

  return (
    <div className="status-page">
      <div className="status-container">
        <h1>Course Generation Status</h1>
        
        <div className="job-info">
          <div className="info-row">
            <strong>Job ID:</strong>
            <code>{jobData.jobId || jobId}</code>
          </div>
          {jobData.createdAt && (
            <div className="info-row">
              <strong>Created:</strong>
              <span>{new Date(jobData.createdAt).toLocaleString()}</span>
            </div>
          )}
          {jobData.updatedAt && (
            <div className="info-row">
              <strong>Last Updated:</strong>
              <span>{new Date(jobData.updatedAt).toLocaleString()}</span>
            </div>
          )}
        </div>

        <div className={`status-badge status-${statusCategory}`}>
          <span className="status-label">
            {statusCategory.toUpperCase()}
            {isPolling && statusCategory !== 'completed' && statusCategory !== 'failed' && (
              <span className="polling-indicator"> ⟳</span>
            )}
          </span>
          <span className="status-text">{statusMessage}</span>
        </div>

        {jobData.error && (
          <div className="error-box">
            <strong>Error Details:</strong>
            <pre>{jobData.error}</pre>
          </div>
        )}

        {jobData.updateLog && jobData.updateLog.length > 0 && (
        <div className="update-log">
            <h2>Update Log</h2>
            <div className="log-entries">
              {jobData.updateLog.map((entry, index) => (
                <div key={index} className="log-entry">
                  <span className="log-time">
                    {entry.time ? new Date(entry.time).toLocaleTimeString() : 'N/A'}
                  </span>
                  <span className="log-message">{entry.message}</span>
                </div>
              ))}
            </div>
            </div>
          )}
      </div>
    </div>
  );
}

