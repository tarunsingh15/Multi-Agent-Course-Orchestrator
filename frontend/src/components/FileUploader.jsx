import { useState, useEffect } from 'react'
import './FileUploader.css'
import FILE_MIME_TYPES from '../fileMimeTypes.json';
import { db } from '../firebase';
import { doc, onSnapshot, setDoc, serverTimestamp, Timestamp } from "firebase/firestore";
import { JsonViewer } from "@textea/json-viewer";
import { v4 as uuidv4 } from 'uuid'; // for generating unique IDs for jobs

import { useNavigate } from "react-router-dom";

// for blueprint review
// added imports for routing and reviewer UI
import { Routes, Route } from "react-router-dom";
import ReviewerBlueprintPage from "./ReviewerBlueprintPage";

import { FaCloudUploadAlt } from 'react-icons/fa';
import { BsBoxArrowUpRight } from 'react-icons/bs';
import StatusModal from './StatusModal';

function FileUploader() {
  // State hooks
  const [selectedFile, setSelectedFile] = useState(null); // The file selected by the user
  const [status, setStatus] = useState(''); // Status messages to show to the user
  const [isUploading, setIsUploading] = useState(false); // Whether a file is being uploaded
  // const [parsedContent, setParsedContent] = useState(''); // The content parsed and returned from backend

  const [jobOutput, setJobOutput] = useState(null); // This will be the job that is created for each uploaded file
  const [listeningId, setListeningId] = useState(null); // The ID of the file we are listening for in Firestore
  const [isStatusModalOpen, setIsStatusModalOpen] = useState(false); // State for status modal

  const [duration, setDuration] = useState(60);   // duration state
  const [context, setContext] = useState(''); // state

  // blooms taxonomy state
  const [selectedBlooms, setSelectedBlooms] = useState([]);
  // blooms taxonomy options
  const blooms_taxonomy = ['remember', 'understand', 'apply'];
  // helper to toggle a bloom value
  const toggleBloom = (b) =>
    setSelectedBlooms((prev) => (prev.includes(b) ? prev.filter((x) => x !== b) : [...prev, b]));
  const cap = (s) => s.charAt(0).toUpperCase() + s.slice(1);

  const MAX_FILE_SIZE = 50 * 1024 * 1024; // 50MB

  const allowedFileTypes = Object.values(FILE_MIME_TYPES);
  const allowedExtensions = Object.keys(FILE_MIME_TYPES).map(ext => `.${ext}`).join(',');

  const navigate = useNavigate(); // initialize navigation

  // useEffect hook: listen for changes in Firestore for the processed file
  useEffect(() => {
    if (!listeningId) return;

    // Create a reference to the document we want to listen to
    const docRef = doc(db, 'jobs', listeningId); // listen to jobs collection in Firestore

    // handle when we get a change in the document
    const unsubscribe = onSnapshot(docRef, (docSnap) => {
      if (docSnap.exists()) {
        const data = docSnap.data();
        setStatus(`Job Status: ${data.status || 'Processing...'} `);
        setJobOutput(data);

        // wait until backend definitely finished fetching from GCS
        if (
          data.status === "BLUEPRINT_COMPLETE" &&
          data.results &&
          Object.keys(data.results.blueprint || {}).length > 0
        ) {
          console.log("Blueprint ready — showing review link instead of auto-redirect.");
          setStatus("Blueprint generation complete! You can now review the course blueprint.");
        } else {
          console.log("Still processing. Current status:", data.status);
        }
      } else {
        console.log("Waiting for the processed document to be created...");
      }
    }, (error) => {
      console.error("Error listening to Firestore:", error);
      setStatus("Error: Could not retrieve processed data.");
    });

    // call unsubscribe when the component unmounts or listeningId changes
    return () => {
      unsubscribe();
    };
  }, [listeningId]);


  // Handle file selection
  const handleFileChange = (event) => {
    const file = event.target.files[0];

    if (!file) return;

    if (!allowedFileTypes.includes(file.type)) {
      setStatus("Error: Only files of valid types are allowed.");
      setSelectedFile(null);
      event.target.value = '';
      return;
    }

    // checks if file size is more than 50 MB;
    if (file.size > MAX_FILE_SIZE) {
      setStatus(`Error: File size exceeds 50MB limit.`);
      setSelectedFile(null);
      event.target.value = '';
      return;
    }
    if (file && allowedFileTypes.includes(file.type)) {
      setSelectedFile(file);
      setJobOutput(null);
      setStatus('');
    }

  };

  // Handle cancel button clicked
  const handleCancel = () => {
    setSelectedFile(null);
    setStatus('');
    setJobOutput(null);
    setListeningId(null);
    document.getElementById('file-upload').value = '';
    navigate('/');
  };

  // handle creating file name
  const generateFileName = (file) => {
    const timestamp = Date.now();
    const ext = file.name.split('.').pop();
    return `${file.name.replace(/\W+/g, "_").toLowerCase()}_${timestamp}.${ext}`;
  };

  // Handle submit button clicked
  const handleSubmit = async () => {
    if (!selectedFile) return;

    // true because file is currently uploading
    setIsUploading(true)
    setJobOutput(null);
    const jobId = uuidv4(); // generate a unique ID for this job
    setListeningId(jobId); // set the ID we are listening for in Firestore

    const backendUrl = 'https://file-uploader-backend-536653873539.us-east4.run.app/generate-upload-url';

    try {
      // Ask our backend for a secure upload URL
      const safeFileName = generateFileName(selectedFile);
      setStatus('Requesting upload permission...');
      const response = await fetch(backendUrl, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          fileName: safeFileName, //selectedFile.name,
          fileType: selectedFile.type,
        }),
      });

      if (!response.ok) {
        throw new Error('Could not get a secure URL from the server.');
      }

      const { url, newFileName } = await response.json();

      // Secure upload URL obtained. Upload the file directly to the secure URL from Google Cloud Storage
      const gcsUri = `gs://mari-uploads-ns-uc1-east4/${newFileName}`;
      setStatus('Uploading file to Google Cloud Storage...');

      const uploadResponse = await fetch(url, {
        method: 'PUT',
        headers: {
          'Content-Type': selectedFile.type,
        },
        body: selectedFile,
      });

      if (!uploadResponse.ok) {
        throw new Error('File upload failed.');
      }

      // wait a few seconds before creating Firestore job
      await new Promise((r) => setTimeout(r, 15000)); // wait 15 seconds

      // create the job document after ensuring file is visible to backend
      const jobRef = doc(db, 'jobs', jobId);
      await setDoc(jobRef, {
        jobId: jobId,
        status: 'PENDING',
        createdAt: serverTimestamp(),
        updateLog: [
          {
            time: Timestamp.now(),
            message: 'Job created after file upload. File uploaded to GCS successfully.',
          }
        ],
        inputs: {
          originalSyllabusGcsUri: gcsUri,
          context: context,
          duration: parseInt(duration),
          bloomsTaxonomy: selectedBlooms,
        },
        results: {},
        error: null
      });

      setStatus(`Upload successful. Orchestrator is processing: ${newFileName}`);
      //setParsedContent('');
      //setListeningId(jobId);
      setSelectedFile(null);
      document.getElementById('file-upload').value = '';
    } catch (error) {
      console.error(error);
      setStatus(`Error: ${error.message}`);
      // If something fails, update the job to failed status
      const jobRef = doc(db, 'jobs', jobId);
      await setDoc(jobRef, { status: 'FAILED', error: error.message }, { merge: true });
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <>
    <Routes>
      {/* existing app route */}
      <Route
        path="/"
        element={
          <div className="uploader-container">
            <div className="uploader-card">
              <h1>Create Your Course</h1>
              <p>
                Upload your content and set the learning objectives.
              </p>
              {/* FILE UPLOAD BOX */}
              <label className="label">File Upload</label>
              {!selectedFile ? (
                <label
                  htmlFor="file-upload"
                  className={`file-upload-area ${isUploading ? 'disabled' : ''}`}
                >
                  <div className="file-upload-icon">
                    <FaCloudUploadAlt />
                  </div>
                  <div className="file-upload-text">
                    Click to upload your course materials
                  </div>
                  <div className="file-upload-hint">
                    PDF, DOCX, or PPTX (MAX. 50MB)
                  </div>
                </label>
              ) : (
                <div className="file-selected-info">
                  <p>Selected File: <strong>{selectedFile.name}</strong></p>
                </div>
              )}
              <input
                type="file"
                id="file-upload"
                className="file-input-hidden"
                data-testid="file-upload"
                accept={allowedExtensions}
                onChange={handleFileChange}
                disabled={isUploading}
              />
              {/* TOTAL COURSE TIME DROPDOWN */}
              <label className="label">Duration: {duration} minutes</label>
              <input
                type="range"
                min="20"
                max="120"
                step="10"
                value={duration}
                onChange={(e) => setDuration(e.target.value)}
                className="slider"
              />
              {/* BLOOMS TAXONOMY CHECKBOXES */}
              <label className="label">Learning objectives</label>
              <div className="checkbox-group">
                {blooms_taxonomy.map((b) => (
                  <label key={b} className="checkbox-item">
                    <input
                      type="checkbox"
                      name="blooms_taxonomy"
                      value={b}
                      checked={selectedBlooms.includes(b)}
                      onChange={() => toggleBloom(b)}
                    />
                    {cap(b)}
                  </label>
                ))}
              </div>

              {/* CONTEXT TEXT AREA */}
              <label className="label">Context</label>
              <textarea
                className="context"
                placeholder={`What would you like to get out of this course?`}
                value={context}
                onChange={(e) => setContext(e.target.value)}
              ></textarea>
              {/* CANCEL BUTTON */}
              <div className="button-container">
                <button
                  onClick={handleCancel}
                  disabled={!selectedFile || isUploading}
                >
                  Cancel
                </button>
                {/* UPLOAD BUTTON */}
                <button
                  onClick={handleSubmit}
                  disabled={!selectedFile || isUploading}
                >
                  {isUploading ? "Uploading..." : "Generate Course"}
                </button>
              </div>

              {status && <p>{status}</p>}

              {isUploading && (
                <div style={{ marginTop: "1rem", color: "gray" }}>
                </div>
              )}

              {!isUploading &&
                jobOutput?.status === "PROCESSING_TEMPLATE" && (
                  <div style={{ marginTop: "1rem", color: "gray" }}>
                    <p>Generating course blueprint... please wait.</p>
                  </div>
                )}

              {!isUploading &&
                jobOutput?.status === "REVISION_REQUESTED" && (
                  <div style={{ marginTop: "1rem", color: "gray" }}>
                    <p>Revision in progress... the blueprint will be updated with your changes.</p>
                  </div>
                )}

              {/* Show Review Blueprint button once ready */}
              {jobOutput?.status === "BLUEPRINT_COMPLETE" &&
                (jobOutput?.results?.blueprint || jobOutput?.results?.blueprint_gcs_uri) && ( // checks if there is a blueprint or blueprint URI in firestore
                  <div style={{ marginTop: "1rem" }}>
                    <button
                      onClick={() =>
                        navigate("/reviewer-blueprint", {
                          state: {
                            blueprint: jobOutput.results.blueprint,
                            jobId: listeningId,
                            profileId: "AYrTvroL62Z3uKhne9Yt", // hardcoded value for profile id for now
                          },
                        })
                      }
                      className="review-btn"
                    >
                      <span>Review Blueprint</span>
                      <BsBoxArrowUpRight />
                    </button>
                  </div>
                )}

              {/* Display Job ID */}
              {listeningId && (
                <div style={{ 
                  marginTop: "1rem", 
                  padding: "0.75rem", 
                  background: "rgba(168, 85, 247, 0.1)", 
                  border: "1px solid #a855f7", 
                  borderRadius: "0.5rem",
                  fontSize: "0.9rem"
                }}>
                  <div style={{ marginBottom: "0.5rem" }}>
                    <strong style={{ color: "#a855f7" }}>Job ID:</strong>{" "}
                    <code style={{ 
                      color: "#e9d5ff", 
                      background: "rgba(0,0,0,0.3)", 
                      padding: "0.2rem 0.5rem", 
                      borderRadius: "0.25rem",
                      wordBreak: "break-all",
                      display: "inline-block",
                      maxWidth: "100%"
                    }}>
                      {listeningId}
                    </code>
                  </div>
                  <div style={{ 
                    display: "flex", 
                    gap: "0.5rem", 
                    flexWrap: "wrap",
                    alignItems: "center"
                  }}>
                    <button
                      onClick={() => {
                        navigator.clipboard.writeText(listeningId);
                        alert("Job ID copied to clipboard!");
                      }}
                      style={{
                        padding: "0.25rem 0.5rem",
                        background: "transparent",
                        border: "1px solid #a855f7",
                        color: "#a855f7",
                        borderRadius: "0.25rem",
                        cursor: "pointer",
                        fontSize: "0.8rem",
                        whiteSpace: "nowrap"
                      }}
                    >
                      Copy
                    </button>
                    <button
                      type="button"
                      onClick={() => setIsStatusModalOpen(true)}
                      style={{
                        padding: "0.25rem 0.75rem",
                        background: "#a855f7",
                        border: "1px solid #a855f7",
                        color: "#ffffff",
                        borderRadius: "0.25rem",
                        cursor: "pointer",
                        fontSize: "0.8rem",
                        fontWeight: "500",
                        whiteSpace: "nowrap"
                      }}
                      title="View detailed status page with live updates"
                    >
                      View Status
                    </button>
                  </div>
                </div>
              )}

              {jobOutput && (
                <div className="parsed-content-container">
                  <JsonViewer
                    value={jobOutput}
                    theme="dark"
                    style={{ padding: "1rem", borderRadius: "0.5rem" }}
                  />
                </div>
              )}
            </div>
          </div>
        }
      />

      <Route path="/reviewer-blueprint" element={<ReviewerBlueprintPage />} />
    </Routes>

    {/* Status Modal */}
    <StatusModal
      jobId={listeningId}
      isOpen={isStatusModalOpen}
      onClose={() => setIsStatusModalOpen(false)}
    />
    </>
  );


}

export default FileUploader