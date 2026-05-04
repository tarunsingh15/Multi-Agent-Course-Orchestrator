import { Routes, Route } from 'react-router-dom';

// Components
import HomePage from './components/HomePage';
import FileUploader from './components/FileUploader';
import ReviewerBlueprintPage from './components/ReviewerBlueprintPage';
import LessonContentPage from './components/LessonContentPage';
import SettingsPage from './components/SettingsPage';
import CourseStatusPage from './components/CourseStatusPage';


function App() {
  return (
    <Routes>
      {/* Homepage with dropdowns */}
      <Route path="/" element={<HomePage />} />

      {/* Reviewer routes */}
      <Route path="/blueprint" element={<ReviewerBlueprintPage />} />
      <Route path="/reviewer-blueprint" element={<ReviewerBlueprintPage />} /> {/* Legacy or alternate route */}

      {/* Lesson content JSON viewer (by jobId) */}
      <Route path="/lesson-content/:jobId" element={<LessonContentPage />} />

      {/* Course generation status page (by jobId) */}
      <Route path="/status/:jobId" element={<CourseStatusPage />} />

      {/* Settings page */}
      <Route path="/settings" element={<SettingsPage />} />

      {/* File Upload */}
      <Route path="/upload/*" element={<FileUploader />} />

      {/* Catch-all route */}
      <Route path="*" element={<HomePage />} />
    </Routes>
  );
}

export default App;