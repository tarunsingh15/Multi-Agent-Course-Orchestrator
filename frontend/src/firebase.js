import { initializeApp } from "firebase/app";
import { getAnalytics } from "firebase/analytics";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyB70D0FpRQNUwXrnivFFIVkPOxx7TzdXxw",
  authDomain: "amazing-math-473517-f9.firebaseapp.com",
  projectId: "amazing-math-473517-f9",
  storageBucket: "amazing-math-473517-f9.firebasestorage.app",
  messagingSenderId: "536653873539",
  appId: "1:536653873539:web:827b8bdd1902a4fc2ab6b6",
  measurementId: "G-B5W1ZWPXH6"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);
const db = getFirestore(app);
const analytics = getAnalytics(app);
export { db };