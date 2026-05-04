import { useNavigate } from 'react-router-dom';
import './HomePage.css';
import { useState } from 'react';
import EmailLogin from './EmailLogin';

function HomePage() {
  const navigate = useNavigate();

  const [session, setSession] = useState({
    isAuthenticated: false,
    uid: null,
    profile: null,
  });

  const handleAuthenticated = (authData) => {
    if (authData) {
      setSession({
        isAuthenticated: true,
        uid: authData.uid,
        profile: authData.profile,
      });
    } else {
      setSession({
        isAuthenticated: false,
        uid: null,
        profile: null,
      });
    }
  };

  const handleNavigateToSettings = () => {
    navigate('/settings', {
      state: {
        learnerProfile: session.profile,
      },
    });
  };

  const isAuthenticated = session.isAuthenticated;

  return (
    <div className="homepage-container">
      <div className="homepage-card">
        <h1 className="homepage-title">Welcome to the MARi Courseware Agent</h1>
        <p className="homepage-subtitle">
          This tool helps instructional designers generate structured course blueprints and configure system settings. Enter your email to load your profile and begin.
        </p>
        <EmailLogin onAuthenticated={handleAuthenticated} />

        <div className="homepage-buttons">
          <button className="homepage-btn blueprint" onClick={() => navigate('/upload')}
            disabled={!isAuthenticated} title={!isAuthenticated ? 'Enter your email to proceed' : ''}>
            Generate Blueprint
          </button>
          <button className="homepage-btn settings" onClick={handleNavigateToSettings}
            disabled={!isAuthenticated} title={!isAuthenticated ? 'Enter your email to proceed' : ''}>
            Settings
          </button>
        </div>
      </div>
    </div>
  );
}

export default HomePage;