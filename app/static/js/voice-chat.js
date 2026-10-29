/**
 * LionFlow AI — Chat vocal (enregistrement micro + envoi au serveur).
 */
(function () {
  'use strict';

  const I18N = window.LF_VOICE_I18N || {};

  document.addEventListener('DOMContentLoaded', function () {
    const recordBtn = document.getElementById('recordBtn');
    const statusEl = document.getElementById('recordStatus');
    const messagesEl = document.getElementById('voiceMessages');
    if (!recordBtn || !statusEl || !messagesEl) return;

    let mediaRecorder = null;
    let audioChunks = [];
    let isRecording = false;
    let sessionId = null;

    function setStatus(text) { statusEl.textContent = text; }

    function appendMessage(role, text, audioUrl) {
      const div = document.createElement('div');
      div.className = 'lf-voice-message ' + (role === 'user' ? 'user' : 'assistant');
      const bubble = document.createElement('div');
      bubble.className = 'lf-voice-bubble';
      bubble.textContent = text;
      div.appendChild(bubble);
      if (audioUrl) {
        const audio = document.createElement('audio');
        audio.controls = true;
        audio.src = audioUrl;
        audio.className = 'lf-voice-audio';
        div.appendChild(audio);
      }
      messagesEl.appendChild(div);
      messagesEl.scrollTop = messagesEl.scrollHeight;
    }

    async function startRecording() {
      try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        audioChunks = [];
        const options = { mimeType: 'audio/webm' };
        mediaRecorder = new MediaRecorder(stream, options);
        mediaRecorder.ondataavailable = (e) => { if (e.data.size > 0) audioChunks.push(e.data); };
        mediaRecorder.onstop = async () => {
          const blob = new Blob(audioChunks, { type: 'audio/webm' });
          stream.getTracks().forEach(t => t.stop());
          await sendAudio(blob);
        };
        mediaRecorder.start();
        isRecording = true;
        recordBtn.classList.add('recording');
        setStatus(I18N.recording || 'Enregistrement…');
      } catch (err) {
        console.error(err);
        setStatus(I18N.error || 'Erreur micro');
      }
    }

    function stopRecording() {
      if (mediaRecorder && mediaRecorder.state !== 'inactive') {
        mediaRecorder.stop();
        isRecording = false;
        recordBtn.classList.remove('recording');
        setStatus(I18N.processing || 'Traitement…');
      }
    }

    async function sendAudio(blob) {
      const formData = new FormData();
      formData.append('audio', blob, 'record.webm');
      if (sessionId) formData.append('session_id', sessionId);

      try {
        const response = await fetch('/voice/api/transcribe', {
          method: 'POST',
          body: formData,
          credentials: 'same-origin',
        });
        const data = await response.json();
        if (!response.ok) {
          setStatus(data.error || I18N.error);
          return;
        }
        sessionId = data.session_id;
        appendMessage('user', data.user_text);
        appendMessage('assistant', data.assistant_text, data.assistant_audio_url);
        // Lecture automatique de la réponse
        if (data.assistant_audio_url) {
          const audio = new Audio(data.assistant_audio_url);
          audio.play().catch(() => {});
        }
        setStatus(I18N.ready || 'Prêt');
      } catch (err) {
        console.error(err);
        setStatus(I18N.error || 'Erreur réseau');
      }
    }

    recordBtn.addEventListener('click', function () {
      if (isRecording) stopRecording();
      else startRecording();
    });
  });
})();