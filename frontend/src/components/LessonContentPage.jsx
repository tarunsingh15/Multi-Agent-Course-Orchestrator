import { useEffect, useState, useMemo } from "react";
import { useParams } from "react-router-dom";
import ReactMarkdown from "react-markdown";
import "./LessonContentPage.css";
import Quiz from "./Quiz";

export default function LessonContentPage() {
  const { jobId } = useParams();

  // Lessons / nav
  const [lessons, setLessons] = useState({});
  const [titles, setTitles] = useState([]);
  const [active, setActive] = useState(null);
  const [progress, setProgress] = useState({});

  // Job status
  const [jobStatus, setJobStatus] = useState(null);
  const [statusError, setStatusError] = useState(null);

  // Quiz state (by module)
  const [quizByModule, setQuizByModule] = useState({});
  const [loadingQuizFor, setLoadingQuizFor] = useState(null);
  const [quizErrorFor, setQuizErrorFor] = useState(null);
  const [passingPercentage, setPassingPercentage] = useState(70);

  // --- helpers ---
  const shuffleArray = (arr) =>
    arr
      .map((item) => ({ ...item, _k: Math.random() }))
      .sort((a, b) => a._k - b._k)
      .map(({ _k, ...rest }) => rest);

  const formatQuestions = (module) =>
    (module?.questions || []).map((q) => ({
      question: q.question_text,
      type: q.question_type,
      justification: q.justification,
      options: shuffleArray(
        (q.options || []).map((o) => ({
          text: o.text,
          isCorrect: o.is_correct,
        }))
      ),
    }));

  // --- 2. Fetch lessons ---
  useEffect(() => {
    async function fetchLessons(retries = 3) {
      try {
        const res = await fetch(
          `https://lesson-generator-api-536653873539.us-east4.run.app/jobs/${jobId}/lessons`
        );
        if (!res.ok) throw new Error("Fetch failed");
        const data = await res.json();
        const map = data.lesson_markdown_by_module || {};
        setLessons(map);

        const keys = Object.keys(map);
        if (keys.length > 0) {
          setTitles(keys);
          setActive((prev) => prev ?? keys[0]);
          const init = {};
          keys.forEach((k, i) => (init[k] = i === 0 ? "in_progress" : "locked"));
          setProgress(init);
        }
      } catch (err) {
        console.error("Failed to load lessons", err);
        if (retries > 0) {
          setTimeout(() => fetchLessons(retries - 1), 5000);
        }
      }
    }
    if (jobId) fetchLessons();
  }, [jobId]);

  // computed flags
  const allCompleted =
    titles.length > 0 && titles.every((t) => progress[t] === "completed");

  const activeQuiz = useMemo(
    () => (active ? quizByModule[active] : []),
    [active, quizByModule]
  );

  // mark module completion + unlock next
  const markCompleted = (title) => {
    const idx = titles.indexOf(title);
    const updated = { ...progress, [title]: "completed" };
    if (idx + 1 < titles.length && updated[titles[idx + 1]] === "locked") {
      updated[titles[idx + 1]] = "in_progress";
    }
    setProgress(updated);
  };

  // --- 3. Fetch quiz only when ready ---
  const fetchQuizForActive = async () => {
    if (!jobId || !active) return;

    if (
      jobStatus === "PROCESSING_LESSON_EVAL" ||
      jobStatus === "LESSON_EVALUATED" ||
      jobStatus === "PROCESSING_QUIZ_GEN"
    ) {
      alert("Quiz is not ready yet — content is still being evaluated.");
      return;
    }

    if (quizByModule[active]?.length) return;

    setQuizErrorFor(null);
    setLoadingQuizFor(active);
    try {
      const res = await fetch(
        `https://quiz-generator-api-536653873539.us-east4.run.app/jobs/${jobId}/quiz`
      );
      if (!res.ok) throw new Error(`Quiz fetch failed: HTTP ${res.status}`);
      const data = await res.json();

      if (typeof data.passing_percentage === "number") {
        setPassingPercentage(data.passing_percentage);
      }

      const module = (data.modules || []).find(
        (m) => m.module_title === active
      );

      if (!module || !module.questions || module.questions.length === 0) {
        throw new Error("No questions available for this module yet.");
      }

      const formatted = formatQuestions(module);

      setQuizByModule((prev) => ({
        ...prev,
        [active]: formatted,
      }));
    } catch (err) {
      console.error("Error loading quiz", err);
      setQuizErrorFor(active);
    } finally {
      setLoadingQuizFor(null);
    }
  };

  // -------------------------------
  // UI RENDERING
  // -------------------------------
  if (!lessons || Object.keys(lessons).length === 0) {
    return <p>Loading lessons...</p>;
  }

  return (
    <div className="lessonPage">

      <aside className="sidebar">
        <h2 className="sidebarTitle">📘 Lessons</h2>
        <ul>
          {titles.map((t) => {
            const state = progress[t];
            const locked = state === "locked";
            return (
              <li
                key={t}
                className={`lessonCard ${active === t ? "active" : ""} ${state}`}
                onClick={() => !locked && setActive(t)}
                aria-disabled={locked}
              >
                <span className="lessonTitle">{t}</span>
                <span className="status">{state}</span>
              </li>
            );
          })}
        </ul>
      </aside>

      {/* Main content */}
      <main className="content">

        {jobStatus === "PROCESSING_LESSON_EVAL" && (
          <div className="statusBanner waiting">
            ⏳ This course is currently being evaluated.
            Quiz generation will begin once evaluation is complete.
          </div>
        )}

        {jobStatus === "LESSON_EVALUATED" && (
          <div className="statusBanner waiting">
            🧪 Lesson evaluation finished — generating revised content or preparing quiz...
          </div>
        )}

        {jobStatus === "PROCESSING_QUIZ_GEN" && (
          <div className="statusBanner waiting">
            ⚙️ Quiz is being generated — please wait...
          </div>
        )}

        {statusError && (
          <div className="statusBanner error">
            ⚠️ Could not fetch job status — the system may be delayed.
          </div>
        )}

        {allCompleted ? (
          <div className="congratsBox">
            <h1>🎉 Congratulations!</h1>
            <p>You’ve completed all the lessons and quizzes. Great work!</p>
          </div>
        ) : (
          <>
            {active ? (
              <>
                <h1>{active}</h1>

                {/* <div className="markdown">
                  <ReactMarkdown>{lessons[active] || ""}</ReactMarkdown>
                </div> */}
                <div className="markdown">
                  <ReactMarkdown
                    components={{
                      a: ({ node, ...props }) => (
                        <a {...props} target="_blank" rel="noopener noreferrer">
                          {props.children}
                        </a>
                      )
                    }}
                  >
                    {lessons[active] || ""}
                  </ReactMarkdown>
                </div>

                <div className="quizFooter">
                  <span>Complete the quiz to unlock the next lesson.</span>

                  <button
                    onClick={fetchQuizForActive}
                    disabled={
                      jobStatus === "PROCESSING_LESSON_EVAL" ||
                      jobStatus === "LESSON_EVALUATED" ||
                      jobStatus === "PROCESSING_QUIZ_GEN" ||
                      !!activeQuiz?.length ||
                      loadingQuizFor === active
                    }
                  >
                    {jobStatus === "PROCESSING_LESSON_EVAL"
                      ? "Waiting for Evaluation…"
                      : jobStatus === "LESSON_EVALUATED"
                        ? "Preparing Revised Content…"
                        : jobStatus === "PROCESSING_QUIZ_GEN"
                          ? "Generating Quiz…"
                          : activeQuiz?.length
                            ? "Quiz Ready"
                            : loadingQuizFor === active
                              ? "Preparing Quiz…"
                              : "Take Quiz"}
                  </button>
                </div>
              </>
            ) : null}
          </>
        )}

        <Quiz
          questions={activeQuiz || []}
          moduleTitle={active}
          jobId={jobId}
          error={quizErrorFor === active}
          loading={loadingQuizFor === active}
          onComplete={() => active && markCompleted(active)}
        />
      </main>
    </div>
  );
}