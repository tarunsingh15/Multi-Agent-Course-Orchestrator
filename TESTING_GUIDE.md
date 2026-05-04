# Testing Guide for Quiz Component Integration

## Current Status ✅

### Frontend
- ✅ Development server running at: **http://localhost:5173**
- ✅ All dependencies installed
- ✅ No linter errors

### Backend APIs
- ✅ Quiz API: `https://quiz-generator-api-536653873539.us-east4.run.app`
- ✅ Lesson API: `https://lesson-generator-api-536653873539.us-east4.run.app`
- ✅ Both APIs are accessible and responding

---

## How to Test the Complete Flow

### Option 1: Full Integration Test (Recommended)

1. **Start the Frontend** (if not already running)
   ```bash
   cd frontend
   npm run dev
   ```

2. **Access the Application**
   - Open browser: http://localhost:5173
   - You should see the "Welcome to the MARi Courseware Agent" homepage

3. **Upload a Document**
   - Click "Generate Blueprint" button
   - Upload a document (PDF, Word, etc.)
   - Wait for blueprint generation

4. **Review Blueprint**
   - Blueprint will be displayed on the reviewer page
   - Click "Create Course" to approve
   - This triggers lesson generation

5. **View Course with Quiz**
   - After lessons are generated, you'll be redirected to `/lesson-content/{jobId}`
   - You should see:
     - Sidebar with lesson modules
     - Markdown lesson content
     - **Interactive Quiz component** at the bottom
     - Old quiz modal (still functional)

6. **Test the Quiz Component**
   - The Quiz component appears automatically at the bottom of the lesson
   - Select answers (radio buttons for single-correct, checkboxes for multi-correct)
   - Click "Submit Quiz"
   - Verify:
     - ✅ Correct/Incorrect feedback appears
     - ✅ Justification text is shown
     - ✅ Cannot change answers after submission
     - ✅ Progress updates when quiz is completed

---

### Option 2: Direct URL Test (Quick Test)

**🎉 Ready-to-Test Job IDs (All have quizzes generated!):**
```
http://localhost:5173/lesson-content/5e010bc2-14db-40c5-b855-7ed2bcdea5f9
http://localhost:5173/lesson-content/37e4bb87-aecb-46d6-a258-6bd4cc27ffa0
http://localhost:5173/lesson-content/49969ede-d6d1-4bf4-98ca-c1dbfe918b46
http://localhost:5173/lesson-content/950e1eec-bca4-4b50-a9d1-ed6b743e042a
http://localhost:5173/lesson-content/e742a536-c041-4d48-8d93-d8e2adf591f8
```

**Other Ways to Find Job IDs:**

#### Method A: From Browser Console
1. Open http://localhost:5173/upload in your browser
2. Open DevTools (F12) → Console tab
3. Upload a file and watch for the job ID in console logs
4. Copy the job ID from the URL or console

#### Method B: From Firebase Console
1. Go to: https://console.firebase.google.com/project/amazing-math-473517-f9/firestore
2. Navigate to the "jobs" collection
3. Find any job with status "QUIZ_GENERATED" or "LESSON_GENERATED"
4. Copy the document ID (this is your job ID)

#### Method C: Create a New Job
Simply upload a new file through the UI:
1. Go to http://localhost:5173/upload
2. Upload any document (PDF, Word, etc.)
3. Complete the full flow (wait for blueprint → approve → generate lessons)
4. You'll automatically be redirected with the job ID in the URL

#### Using the Job ID
Once you have a job ID, navigate directly to lesson content:
```
http://localhost:5173/lesson-content/YOUR-JOB-ID
```

**Verify Quiz appears**
- Quiz should load automatically at the bottom
- Questions should populate from the quiz API

---

## Testing the Quiz API Directly

You can test the backend quiz API independently:

```bash
# Replace YOUR-JOB-ID with an actual job ID
curl https://quiz-generator-api-536653873539.us-east4.run.app/jobs/YOUR-JOB-ID/quiz
```

**Expected Responses:**
- `200 OK`: Quiz data returned successfully
- `202 Accepted`: Quiz still processing
- `404 Not Found`: Quiz not found or not generated yet
- `500 Error`: Server error

---

## Quiz Component Features to Verify

### ✅ Visual Appearance
- Dark theme matches the lesson page
- Purple accent color (#a855f7) used throughout
- Smooth hover transitions
- Clean spacing and typography

### ✅ Functionality
- Radio buttons for `single_correct` questions
- Checkboxes for `multi_correct` questions
- Submit button disabled until at least one answer selected
- After submission:
  - ✅ Shows "Correct!" or "Incorrect" for each question
  - ✅ Displays justification text
  - ✅ Disables answer changes
  - ✅ Calls `onComplete()` callback
  - ✅ Updates lesson progress

### ✅ Data Handling
- Questions load from API automatically
- Formats API response correctly
- Handles empty question sets gracefully
- Retries if API is temporarily unavailable

---

## Troubleshooting

### Quiz Not Showing
1. Check browser console for errors
2. Verify job has quiz data:
   ```bash
   curl https://quiz-generator-api-536653873539.us-east4.run.app/jobs/JOB-ID/quiz
   ```
3. Check that quiz was generated (status should be "QUIZ_GENERATED")

### Quiz Questions Not Loading
1. Open browser DevTools (F12)
2. Go to Network tab
3. Look for requests to quiz API
4. Check for 200 status codes
5. Verify API responses contain question data

### Styling Issues
- Quiz component uses existing CSS file: `Quiz.css`
- Should inherit dark theme from `LessonContentPage.css`
- If colors look wrong, check CSS variables

---

## Quick Test Checklist

- [ ] Frontend server running at localhost:5173
- [ ] Homepage loads without errors
- [ ] Can navigate to lesson content page
- [ ] Quiz component appears at bottom of lesson
- [ ] Questions load and display correctly
- [ ] Can select answers (radio/checkbox)
- [ ] Submit button works
- [ ] Feedback appears after submission
- [ ] Cannot change answers after submission
- [ ] Progress updates correctly
- [ ] Old quiz modal still functions independently

---

## Need Help?

If you encounter issues:
1. Check browser console for errors
2. Verify backend APIs are accessible
3. Ensure you have a valid job ID
4. Check that quiz was generated for that job
5. Review the LessonContentPage.jsx code for the quiz integration

