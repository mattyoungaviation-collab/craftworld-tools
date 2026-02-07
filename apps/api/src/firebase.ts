import admin from 'firebase-admin';

let app: admin.app.App | null = null;

export const isFirebaseConfigured = () =>
  Boolean(process.env.FIREBASE_PROJECT_ID && process.env.FIREBASE_CLIENT_EMAIL && process.env.FIREBASE_PRIVATE_KEY);

const initFirebase = () => {
  if (app || !isFirebaseConfigured()) return app;
  const projectId = process.env.FIREBASE_PROJECT_ID as string;
  const clientEmail = process.env.FIREBASE_CLIENT_EMAIL as string;
  const privateKey = (process.env.FIREBASE_PRIVATE_KEY as string).replace(/\\n/g, '\n');

  app = admin.initializeApp({
    credential: admin.credential.cert({ projectId, clientEmail, privateKey })
  });
  return app;
};

export const createCustomToken = async (uid: string, claims?: Record<string, unknown>) => {
  initFirebase();
  if (!app) throw new Error('Firebase not configured');
  return admin.auth().createCustomToken(uid, claims);
};

export const verifyIdToken = async (token: string) => {
  initFirebase();
  if (!app) throw new Error('Firebase not configured');
  return admin.auth().verifyIdToken(token);
};
