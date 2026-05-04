import { useState, useEffect, useMemo } from "react";
import "./Quiz.css";

// Helper function to shuffle array
const shuffleArray = (arr) =>
  arr
    .map((item) => ({ ...item, _k: Math.random() }))
    .sort((a, b) => a._k - b._k)
    .map(({ _k, ...rest }) => rest);

export default function Quiz({ questions = [], onComplete, passingPercentage = 70 }) {
  const [answers, setAnswers] = useState({});
  const [submitted, setSubmitted] = useState(false);
  const [retakeKey, setRetakeKey] = useState(0);

  // Hook 1
  const shuffledQuestions = useMemo(() => {
    if (!questions.length) return [];
    const shuffled = shuffleArray([...questions]);
    return shuffled.map((q) => ({
      ...q,
      options: shuffleArray([...q.options]),
    }));
  }, [questions, retakeKey]);

  // Hook 2
  useEffect(() => {
    setAnswers({});
    setSubmitted(false);
    setRetakeKey(0);
  }, [questions]);

  const handleSelect = (qIdx, optIdx, type) => {
    if (type === "multi_correct" || type === "select_all") {
      const prev = answers[qIdx] || [];
      const next = prev.includes(optIdx)
        ? prev.filter((v) => v !== optIdx)
        : [...prev, optIdx];
      setAnswers({ ...answers, [qIdx]: next });
    } else if (type === "true_false") {
      setAnswers({ ...answers, [qIdx]: [optIdx] });
    } else {
      setAnswers({ ...answers, [qIdx]: [optIdx] });
    }
  };

  // Hook 3: Check if all questions are answered
  const allQuestionsAnswered = useMemo(() => {
    return shuffledQuestions.every((_, qIdx) => {
      const answer = answers[qIdx];
      return answer && answer.length > 0;
    });
  }, [shuffledQuestions, answers]);

  // Hook 4: Calculate score
  const score = useMemo(() => {
    if (shuffledQuestions.length === 0) return { score: 0, total: 0, percentage: 0 };
    
    let correct = 0;
    shuffledQuestions.forEach((q, qIdx) => {
      const selected = answers[qIdx] || [];
      const correctIndices = q.options
        .map((opt, i) => (opt.isCorrect ? i : null))
        .filter((i) => i !== null);
      
      if (q.type === "multi_correct" || q.type === "select_all") {
        const isCorrect =
          selected.length === correctIndices.length &&
          selected.every((i) => correctIndices.includes(i)) &&
          correctIndices.every((i) => selected.includes(i));
        if (isCorrect) correct++;
      } else {
        if (selected.length === 1 && correctIndices.includes(selected[0])) {
          correct++;
        }
      }
    });
    
    const total = shuffledQuestions.length;
    const percentage = total > 0 ? Math.round((correct / total) * 100) : 0;
    return { score: correct, total, percentage };
  }, [shuffledQuestions, answers]);

  const passed = submitted && score.percentage >= passingPercentage;

  const handleSubmit = () => {
    if (!allQuestionsAnswered) return;
    
    const currentPassed = score.percentage >= passingPercentage;
    setSubmitted(true);
    if (onComplete && currentPassed) {
      onComplete();
    }
  };

  const handleRetake = () => {
    setAnswers({});
    setSubmitted(false);
    setRetakeKey((prev) => prev + 1);
  };

  const getInputType = (type) => {
    if (type === "multi_correct" || type === "select_all") return "checkbox";
    if (type === "true_false") return "radio";
    return "radio";
  };

  // --- MOVED CHECK HERE ---
  // Only return null AFTER all hooks have run
  if (!questions.length) return null;

  return (
    <div className="quiz-container">
      <h3>📝 Module Quiz</h3>
      
      {submitted && (
        <div className={`score-display ${passed ? "passed" : "failed"}`}>
          <p className="score-text">
            Score: {score.score} / {score.total} ({score.percentage}%)
          </p>
          <p className="score-status">
            {passed 
              ? `Passed! You need ${passingPercentage}% to proceed.` 
              : `Did not pass. You need ${passingPercentage}% to proceed. Please retake the quiz.`}
          </p>
        </div>
      )}

      {shuffledQuestions.map((q, qIdx) => {
        const selected = answers[qIdx] || [];
        const isAnswered = selected.length > 0;
        const correctIndices = q.options
          .map((opt, i) => (opt.isCorrect ? i : null))
          .filter((i) => i !== null);
        
        let isCorrect = false;
        if (submitted && isAnswered) {
          if (q.type === "multi_correct" || q.type === "select_all") {
            isCorrect =
              selected.length === correctIndices.length &&
              selected.every((i) => correctIndices.includes(i)) &&
              correctIndices.every((i) => selected.includes(i));
          } else {
            isCorrect = selected.length === 1 && correctIndices.includes(selected[0]);
          }
        }

        return (
          <div key={qIdx} className={`question-block ${!isAnswered && !submitted ? "unanswered" : ""}`}>
            <p className="question-text">
              {q.question}
              {q.type === "select_all" && <span className="question-hint"> (Select all that apply)</span>}
              {q.type === "true_false" && <span className="question-hint"> (True/False)</span>}
            </p>
            <ul className="options-list">
              {q.options.map((opt, optIdx) => (
                <li key={optIdx}>
                  <label>
                    <input
                      type={getInputType(q.type)}
                      name={`q-${qIdx}`}
                      checked={selected.includes(optIdx)}
                      disabled={submitted}
                      onChange={() => handleSelect(qIdx, optIdx, q.type)}
                    />
                    {opt.text}
                  </label>
                </li>
              ))}
            </ul>

            {submitted && (
              <div className={`feedback ${isCorrect ? "correct" : "incorrect"}`}>
                <p><strong>Justification:</strong> {q.justification}</p>
                <p>{isCorrect ? "Correct!" : "Incorrect."}</p>
              </div>
            )}
          </div>
        );
      })}

      {!submitted ? (
        <div className="quiz-actions">
          {!allQuestionsAnswered && (
            <p className="validation-message">
              ⚠️ Please answer all questions before submitting.
            </p>
          )}
          <button 
            className="submit-btn" 
            onClick={handleSubmit}
            disabled={!allQuestionsAnswered}
          >
            Submit Quiz
          </button>
        </div>
      ) : (
        <div className="quiz-actions">
          <button className="submit-btn" onClick={handleRetake}>
            Retake Quiz
          </button>
        </div>
      )}
    </div>
  );
}
