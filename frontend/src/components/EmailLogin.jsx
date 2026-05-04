import { useState, useEffect } from "react";
import './EmailLogin.css';
import { resolveEmail } from '../api/sessionClient';
import { getUid, setUid, getEmail, setEmail } from '../services/session';


export default function EmailLogin({ onAuthenticated }) {
    const [email, setEmailInput] = useState('');
    const [isEditing, setIsEditing] = useState(false);
    const [isLoading, setIsLoading] = useState(false);
    const [status, setStatus] = useState({ message: '', type: 'idle' });

    useEffect(() => {
        const existingUid = getUid();
        const existingEmail = getEmail();

        if (existingUid && existingEmail) {
            setEmailInput(existingEmail);
            setIsEditing(false);
            // fetch the profile
            handleEmailSubmit(existingEmail, true);
        } else {
            setIsEditing(true);
        }
    }, []);

    const handleEmailSubmit = async (emailToSubmit, isAutoFetch = false) => {
        setIsLoading(true);
        setStatus({ message: isAutoFetch ? 'Loading profile..' : 'Resolving email..', type: 'idle' });

        try {
            const { uid, profile, created } = await resolveEmail(emailToSubmit);

            // saving session to localStorage
            setUid(uid);
            setEmail(emailToSubmit);

            // notifying parent component
            if (onAuthenticated) {
                onAuthenticated({ uid, profile });
            }

            const successMessage = created 
            ? "Welcome! A new profile was created for you"
            : "Welcome back! Your preferences have loaded.";

            setStatus({ message: successMessage, type: 'success' });
            if (!isAutoFetch){
                setIsEditing(false);
            }
        }
        catch (err) {
            console.error(err);
            setStatus({ message: err?.message || 'Failed to resolve email', type: 'error' });
            if (onAuthenticated) { onAuthenticated(null); }
            setIsEditing(true);
        }
        finally { setIsLoading(false); }
    };

    const handleSubmitForm = (e) => {
        e.preventDefault();
        if (email) { handleEmailSubmit(email); }
    };

    const handleEmailChange = (e) => {
        setEmailInput(e.target.value);
        if (status.message) {
            setStatus({ message: '', type: 'idle' });
        }
    };

    const handleChangeClick = () => {
        if (onAuthenticated) {  onAuthenticated(null);   }

        localStorage.removeItem('session.uid');
        localStorage.removeItem('session.email');

        setEmailInput('');
        setStatus({ message: '', type: 'idle'});
        setIsEditing(true);
        setIsLoading(false);
    };

    return (
        <form className="email-form-container" onSubmit={handleSubmitForm}>
            <div className="email-input-group">
                <input
                    type="email"
                    value={email}
                    onChange={handleEmailChange}
                    placeholder="you@example.com"
                    className="email-input"
                    disabled={!isEditing || isLoading}
                    required
                    aria-label="Email Address"
                />

                {isEditing ? (
                    <button
                        type="submit"
                        className="email-submit-btn"
                        disabled={isLoading || !email}
                    >
                        {isLoading ? 'Loading...' : 'Submit'}
                    </button>
                ) : (
                    <button
                        type="button"
                        className="email-edit-btn"
                        onClick={handleChangeClick}
                        disabled={isLoading}
                    >
                        Change
                    </button>
                )
                }
            </div>
            {status.message && (
                <p className={`email-status-message ${status.type}`}>
                    {status.message}
                </p>
            )}
        </form>
    );
}