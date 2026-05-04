/** deploy command

gcloud run deploy file-uploader-backend --source . --region us-east4 --service-account file-uploader-sa@amazing-math-473517-f9.iam.gserviceaccount.com --allow-unauthenticated

 */

import express from 'express';
import cors from 'cors';
import { Storage } from '@google-cloud/storage';
import { randomUUID } from 'crypto';
import * as path from 'path';
import fs from 'fs';

const FILE_MIME_TYPES = JSON.parse(
  fs.readFileSync(path.resolve('./fileMimeTypes.json'), 'utf8')
);

// Initialize the server and the storage client
const app = express();
const storage = new Storage();

/** CORS configuration: cors-config.json 
  This file sets up CORS for the specific bucket this bucket service account has access to.
  If you need to change CORS settings, modify cors-config.json and re-run this command:

    gcloud storage buckets update gs://mari-uploads-ns-uc1-east4 --cors-file=cors-config.json

  Make sure the allowed origin specified below matches the origin in cors-config.json
 */
const allowedOrigin = 'https://react-frontend-536653873539.us-east4.run.app';
app.use(cors({ origin: allowedOrigin }));
app.use(express.json()); // Middleware to parse JSON request bodies

const BUCKET_NAME = 'mari-uploads-ns-uc1-east4';
const allowedMimeTypes = new Set(Object.values(FILE_MIME_TYPES));

//  API endpoint that is called by the frontend React app
app.post('/generate-upload-url', async (req, res) => {
  // Get file type from the request body
  const { fileType, fileName } = req.body;

  if (!fileName || !fileType) {
    return res.status(400).send({ error: 'Missing required parameters: fileName and fileType' });
  }

  // Validate file type
  if (!allowedMimeTypes.has(fileType)) {
    return res.status(400).send({ error: `Invalid file type. Allowed types: ${Array.from(allowedMimeTypes).join(', ')}` });
  }

  const fileExtension = path.extname(fileName);
  const uniqueFileName = `${randomUUID()}${fileExtension}`;

  // Set the options for the secure URL.
  const options = {
    version: 'v4',
    action: 'write',
    expires: Date.now() + 60 * 1000 * 15, // expires in the next 15 minutes
    contentType: fileType,
  };

  try {
    // Generate the signed URL from Google Cloud Storage
    const [url] = await storage
      .bucket(BUCKET_NAME)
      .file(uniqueFileName)
      .getSignedUrl(options);

    // Send the secure URL back to the frontend
    res.status(200).json({ url, newFileName: uniqueFileName });
  } catch (err) {
    console.error('Failed to generate signed URL', err);
    res.status(500).send({ error: 'Internal Server Error' });
  }
});

// Start server
const port = process.env.PORT || 8080;
app.listen(port, () => {
  console.log(`Backend server listening on port ${port}`);
});
