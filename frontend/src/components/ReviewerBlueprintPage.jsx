import { useLocation, useNavigate } from "react-router-dom";
import { useState, useEffect } from "react";
import './ReviewerBlueprintPage.css'
import { BsChevronUp, BsChevronDown, BsArrowUp } from "react-icons/bs";

export default function ReviewerBlueprintPage() {

  const location = useLocation();
  const navigate = useNavigate();

  const blueprintFromState = location.state?.blueprint || null;
  const jobId = location.state?.jobId;
  const profileId = location.state?.profileId || "AYrTvroL62Z3uKhne9Yt";

  const [feedbackSent, setFeedbackSent] = useState(false);
  const [feedbackText, setFeedbackText] = useState("");
  const [jobData, setJobData] = useState(null);
  const [currentBlueprint, setCurrentBlueprint] = useState(blueprintFromState);
  const [isPolling, setIsPolling] = useState(false);
  const [isProfileOpen, setIsProfileOpen] = useState(true);
  const [isGeneratingLesson, setIsGeneratingLesson] = useState(false);
  const [isRevising, setIsRevising] = useState(false);

  useEffect(() => {
    if (!jobId) return;

    let interval = null;

    const pollJob = async () => {
      try {
        const res = await fetch(`https://profiles-api-536653873539.us-central1.run.app/jobs/${jobId}`);
        if (res.ok) {
          const data = await res.json();
          setJobData(data);

          const blueprintUri = data.results?.blueprint_gcs_uri;
          
          if (data.status === "BLUEPRINT_COMPLETE") {
             if (blueprintUri) {
                const blueprintRes = await fetch(
                  `https://profiles-api-536653873539.us-central1.run.app/blueprint/${jobId}`
                );
                if (blueprintRes.ok) {
                  const blueprintJson = await blueprintRes.json();
                  setCurrentBlueprint(blueprintJson);
                }
             } else if (data.results?.blueprint) {
                setCurrentBlueprint(JSON.parse(JSON.stringify(data.results.blueprint)));
             }
             
             if (isRevising || isPolling) {
                 setIsPolling(false);
                 setFeedbackSent(false);
                 setIsRevising(false);
             }
          }
          
          if (data.status === "FAILED") {
             setIsPolling(false);
             setIsRevising(false);
          }
        }
      } catch (err) {
        console.error("Polling failed", err);
      }
    };

    const isIncomplete = jobData?.status && 
                         jobData.status !== "BLUEPRINT_COMPLETE" && 
                         jobData.status !== "FAILED";

    if (isIncomplete || isPolling) {
      pollJob();
      interval = setInterval(pollJob, 3000);
    } else {
      pollJob();
    }

    return () => {
      if (interval) clearInterval(interval);
    };
  }, [jobId, isPolling, jobData?.status]);


  const handleFeedback = async (decision) => {
    if (!jobId) {
      alert("Error: No job ID found.");
      return;
    }

    if (decision === "revision" && !feedbackText.trim()) {
        alert("Please provide specific feedback for the revision.");
        return;
    }

    try {
      if (decision === "revision") {
          setIsRevising(true);
          setFeedbackSent(true);
      }

      const response = await fetch(
        `https://profiles-api-536653873539.us-central1.run.app/blueprint/${jobId}/feedback`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            reviewer_id: profileId,
            reviewer_name: "ProfileUser",
            decision: decision === "approved" ? "approved" : "revision",
            comments: feedbackText || (decision === "approved" ? "Looks good." : "Needs revisions."),
          }),
        }
      );

      if (!response.ok) throw new Error("Failed to submit feedback");

      setFeedbackText("");

      if (decision === "revision") {
        setJobData({ status: "REVISION_REQUESTED" });
        setIsPolling(true);
      }

      if (decision === "approved") {
        setIsGeneratingLesson(true);
        
        alert("Generating lessons... This may take a few minutes. You will be redirected automatically.");
        
        try {
            const genRes = await fetch(
              `https://lesson-generator-api-536653873539.us-east4.run.app/jobs/${jobId}/generate_lessons`,
              { method: "POST" }
            );

            if (genRes.ok) {
                let isReady = false;
                const pollUrl = `https://profiles-api-536653873539.us-central1.run.app/jobs/${jobId}`;
                
                for (let i = 0; i < 120 && !isReady; i++) { // Poll for up to 10 mins (120 * 5s)
                    try {
                        const res = await fetch(pollUrl);
                        if (res.ok) {
                            const data = await res.json();
                            const status = data.status;
                            
                            const validStates = [
                                "LESSON_CRITIQUE_COMPLETE", 
                                "PROCESSING_QUIZ_GEN", 
                                "QUIZ_GENERATED", 
                                "PROCESSING_QUIZ_EVAL", 
                                "EVALUATION_COMPLETE"
                            ];

                            if (validStates.includes(status)) {
                                isReady = true;
                            }
                            
                            if (status === "FAILED") {
                                throw new Error("Job failed during generation.");
                            }
                        }
                    } catch (e) {
                        console.warn("Polling error:", e);
                    }
                    
                    if (!isReady) await new Promise(r => setTimeout(r, 5000)); 
                }
                
                if (isReady) {
                   navigate(`/lesson-content/${jobId}`);
                } else {
                   setIsGeneratingLesson(false);
                   alert("Course generation timed out. Please check dashboard.");
                }
            } else {
                throw new Error("Failed to start lesson generation");
            }
        } catch (err) {
            console.error(err);
            setIsGeneratingLesson(false);
            alert("Error generating course.");
        }
      }
    } catch (error) {
      console.error(error);
      alert("Error submitting feedback");
      setIsRevising(false);
      setFeedbackSent(false);
      setIsGeneratingLesson(false);
    }
  };

  
  if (!currentBlueprint && !jobData) {
    return (
      <div className="p-6"><p className="text-gray-600 font-medium animate-pulse">Loading blueprint data...</p></div>
    );
  }

  if (!currentBlueprint && jobData && !isRevising) {
      return <div className="p-6"><p className="text-red-600">No blueprint data available.</p></div>;
  }

  const blueprint = currentBlueprint || { course_title: "Updating...", modules: [] };

  return (
    <div className="reviewer-page-layout">

      <div className="reviewer-sidebar">
        {jobData?.learnerProfile && (
          <div className="profile-container">
            <button className="profile-toggle-btn" onClick={() => setIsProfileOpen(!isProfileOpen)}>
              <span>Learner Profile</span>
              {isProfileOpen ? <BsChevronUp /> : <BsChevronDown />}
            </button>
            {isProfileOpen && (
              <div className="profile-details">
                <p><strong>Complexity:</strong> {jobData.learnerProfile.complexity}</p>
                <p><strong>Tone:</strong> {jobData.learnerProfile.tone}</p>
                <p><strong>Learning Styles:</strong> {jobData.learnerProfile.learningStyles?.join(", ")}</p>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="reviewer-main-content">
        
        <div className={`blueprint-container ${isRevising ? "opacity-50 pointer-events-none" : ""}`}>
          <h1 className="text-3xl font-bold">[Title] {blueprint.course_title}</h1>
          <p className="text-lg text-gray-300">[Description] {blueprint.course_description}</p>

          {blueprint.modules.map((mod, i) => (
            <div key={i} className="module-card">
              <h2 className="text-xl font-semibold text-yellow-300">[Module {i}] {mod.module_title}</h2>
              <p className="text-sm text-gray-400">Estimated time: {mod.estimated_minutes} min</p>
              <h3 className="mt-2 font-medium text-gray-300">Learning Objectives</h3>
              <ul className="list-disc list-inside text-gray-400">
                {mod.learning_objectives.map((obj, j) => <li key={j}>{obj}</li>)}
              </ul>
              {mod.assessment_questions?.length > 0 && (
                <>
                  <h3 className="mt-2 font-medium text-gray-300">Assessment Questions</h3>
                  <ul className="list-disc list-inside text-gray-400">
                    {mod.assessment_questions.map((q, k) => <li key={k}>{q}</li>)}
                  </ul>
                </>
              )}
            </div>
          ))}
        </div>

        <div className="feedback-container">
          <div className="feedback-left">
            {jobData?.status === "REVISION_REQUESTED" && (
              <div className="status-msg">Requesting revisions...</div>
            )}
            {isPolling && !isRevising && (
               <div className="status-msg">Creating new blueprint...</div>
            )}
            {isRevising && (
                <div className="status-msg animate-pulse">AI Agent is applying revisions...</div>
            )}
            {jobData?.status === "BLUEPRINT_COMPLETE" && !isRevising && (
              <div className="status-msg">Showing the most recent blueprint revisions.</div>
            )}
            {isGeneratingLesson && (
              <div className="status-msg text-yellow-400 animate-pulse">
                 Generating Course Content... (Check Status in Console)
              </div>
            )}
          </div>

          <div className="feedback-center">
            {!feedbackSent && !isGeneratingLesson ? (
              <div className="feedback-input-group">
                <textarea
                  value={feedbackText}
                  onChange={(e) => setFeedbackText(e.target.value)}
                  placeholder="What would you like to revise or improve?"
                  className="feedback-textbox"
                  rows={3}
                />
                <button
                  onClick={() => handleFeedback("revision")}
                  className="revise-button"
                  title="Request Revision"
                >
                  <BsArrowUp />
                </button>
              </div>
            ) : (
               <div className="p-4 text-gray-400 italic">
                 {isGeneratingLesson 
                    ? "Course generation in progress. Please wait..." 
                    : "Feedback submitted. Waiting for AI..."}
               </div>
            )}
          </div>

          <div className="feedback-right p-4">
            {/* FIX 3: Hide button if feedback sent OR generating lesson */}
            {!feedbackSent && !isGeneratingLesson && (
              <button
                className="approve-button"
                onClick={() => handleFeedback("approved")}
              >
                Create Course
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
