import { useEffect, useMemo, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { profileApi, diffProfile } from '../api/profileClient';

/*
 Hard-coding the Profile ID for now
This can be later passed from the parent component or as a URL parameter 'profile_id'
The current code handles both these inputs.*/
// const PROFILE_ID = 'AYrTvroL62Z3uKhne9Yt';

// VALUES FOR ALL THE OPTIONS
const COMPLEXITY = ['beginner', 'intermediate', 'advanced'];
const TONE = ['casual', 'neutral', 'formal'];
const LEARNING_STYLES = ['visual', 'reading', 'example-based', 'analytical', 'formal', 'abstract', 'conceptual', 'analogies'];


const default_val = {
    complexity: 'intermediate',
    learningStyles: ['reading'],
    tone: 'casual',
};
const make_label = (s) => s.replace(/-/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());

export default function SettingsPage({ profileId: profileIdParam }) {   //profile Id can be passed from the URL
    const location = useLocation();
    const navigate = useNavigate();
    const profileFromState = location.state?.learnerProfile;

    const [currentId, setCurrentId] = useState('');

    const [profile, setProfile] = useState(default_val);
    const [original, setOriginal] = useState(null);
    const [status, setStatus] = useState({ kind: 'idle', msg: '' });
    const [loading, setLoading] = useState(true);

    // Loading the profile
    useEffect(() => {
        if (profileFromState && profileFromState.id) {
            setCurrentId(profileFromState.id);

            const snapshot = {
                id: profileFromState.id,
                uid: profileFromState.uid,
                complexity: profileFromState?.complexity ?? default_val.complexity,
                tone: profileFromState?.tone ?? default_val.tone,
                learningStyles: Array.isArray(profileFromState?.learningStyles) ? profileFromState.learningStyles : [],
            };

            setProfile(snapshot);
            setOriginal(snapshot);
            setStatus({kind: 'ok', msg: `Profile ${snapshot.uid} loaded`});
            setLoading(false);
        }
        else {
            setStatus({kind: 'error', msg: `No Profile loaded, Enter email address on Home page`});
            setLoading(false);
        }
    }, [profileFromState]);

    // check if there are changes
    const changed = useMemo(() => diffProfile(original, profile), [original, profile]);
    const hasChanges = useMemo(() => Object.keys(changed).length > 0, [changed]);

    //  Handlers
    const setField = (k, v) => setProfile(p => ({ ...p, [k]: v }));
    const toggleStyle = (style) => {
        setProfile(p => {
            const set = new Set(p.learningStyles || []);
            set.has(style) ? set.delete(style) : set.add(style);
            return { ...p, learningStyles: Array.from(set) };
        });
    };

    // Updating changes on the profile
    const onSave = async () => {
        if (!currentId) { setStatus({ kind: 'error', msg: 'Missing profile Id. Cannot save' }); return; }
        if (!hasChanges) { setStatus({ kind: 'info', msg: 'No changes to save.' }); return; }

        setLoading(true);
        setStatus({ kind: 'progress', msg: 'Applying partial update...' });
        try {
            const saved = await profileApi.patch(currentId, changed);
            const snapshot = saved ?? { ...original, ...changed };
            setOriginal(snapshot);
            setProfile(snapshot);
            setStatus({ kind: 'ok', msg: `Saved fields: ${Object.keys(changed).join(', ')}` });
        } catch (e) {
            setStatus({ kind: 'error', msg: `Save failed: ${e.message}` });
        } finally {
            setLoading(false);
        }
    };

    const onReset = async () => {
        if (!currentId) { setStatus({ kind: 'error', msg: 'Missing profile Id. Cannot reset' }); return; }

        const resetChanges = { ...default_val };

        setLoading(true);
        setStatus({ kind: 'progress', msg: 'Resetting to defaults..' });

        try {
            const saved = await profileApi.patch(currentId, resetChanges);
            const snapshot = saved ?? {...original, ...resetChanges};
            setOriginal(snapshot);
            setProfile(snapshot);
            setStatus({ kind: 'ok', msg: 'Profile reset to defaults' });
        } catch (e) {
            setStatus({ kind: 'error', msg: `Reset failed ${e.message}` });
            if (original) setProfile(original);
        } finally {
            setLoading(false);
        }
    };

    const disabled = loading;

    const complexityIndex = Math.max(0, COMPLEXITY.indexOf(profile.complexity));
    const onComplexitySlide = (e) => {
        const idx = Number(e.target.value);
        const val = COMPLEXITY[idx] || COMPLEXITY[0];
        setField('complexity', val); // stores lowercase; UI shows Title Case
    };

    return (
        <section className="card settings-card">
            <h2>Learner Profile — Settings</h2>

            {/* showing which profile is being edited */}
            <p className="text-muted" style={{ marginTop: '-4px' }}>
                User ID: <strong>{profile.uid || '(none)'}</strong>
            </p>

            {/* Status */}
            {status.msg && (
                <p
                    className={
                        status.kind === 'error' ? 'text-error' :
                            status.kind === 'progress' ? 'text-info' :
                                status.kind === 'ok' ? 'text-success' :
                                    'text-muted'
                    }
                    style={{ minHeight: 24 }}
                >
                    {status.msg}
                </p>
            )}

            {/* Complexity */}
            <div className="form-row">
                <label htmlFor="complexity"><strong>Complexity</strong></label>
                <input
                    id="complexity"
                    type="range"
                    min="0"
                    max={COMPLEXITY.length - 1}
                    step="1"
                    value={complexityIndex}
                    onChange={onComplexitySlide}
                    disabled={disabled}
                />
                <div className="slider-labels">
                    {COMPLEXITY.map((c, i) => (
                        <span key={c} className={i === complexityIndex ? 'active' : ''}>
                            {make_label(c)}
                        </span>
                    ))}
                </div>
            </div>

            {/* Learning Styles */}
            <div className="form-row">
                <label><strong>Learning Styles</strong></label>
                <div className="checkbox-grid">
                    {LEARNING_STYLES.map(style => (
                        <label key={style} className="checkbox-item">
                            <input
                                type="checkbox"
                                checked={profile.learningStyles.includes(style)}
                                onChange={() => toggleStyle(style)}
                                disabled={disabled}
                            />
                            <span>{make_label(style)}</span>
                        </label>
                    ))}
                </div>
            </div>

            {/* Tone */}
            <div className="form-row">
                <label htmlFor="tone"><strong>Tone</strong></label>
                <div className="chip-row">
                    {TONE.map(t => {
                        const selected = profile.tone === t;
                        return (
                            <button
                                key={t}
                                type="button"
                                className={`chip ${selected ? 'chip--selected' : ''}`}
                                aria-pressed={selected}
                                onClick={() => setField('tone', t)}
                                disabled={disabled}
                            >
                                {make_label(t)}
                            </button>
                        );
                    })}
                </div>
            </div>

            {/* Actions */}
            <div className="button-row">
                <button type="button" onClick={onSave} disabled={disabled || !hasChanges}>
                    Save
                </button>
                <button type="button" className="secondary" onClick={onReset} disabled={disabled}>
                    Reset
                </button>
            </div>

            {/* Return to Home Button */}
            <div className="return-home-container">
                <button type="button" className="return-home-btn" onClick={() => navigate('/')}>
                    Return to Home
                </button>
            </div>
        </section>
    );
}