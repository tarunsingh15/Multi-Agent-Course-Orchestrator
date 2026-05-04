/*
Resuable helper functions that services can use to read the UID and user email.
(Using localStorage to make sure the values survive a page reload)

To get the uid:

import {getUid, getEmail} from '../services/session';

const uid = getUid();
const emial = getEmail(); 
*/

const UID_KEY = 'session.uid';
const EMAIL_KEY = 'session.email';

export function getUid() {
    return localStorage.getItem(UID_KEY);
}

export function setUid(uid) {
    localStorage.setItem(UID_KEY, uid);
}

export function getEmail() {
    return localStorage.getItem(EMAIL_KEY);
}

export function setEmail(email){
    localStorage.setItem(EMAIL_KEY, email);
}