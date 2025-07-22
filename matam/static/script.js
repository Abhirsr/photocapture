const video = document.getElementById("video");
const formSection = document.getElementById("form-section");

let storedEmail = null;
let emailSent = false;
let requestId = null;

// 📷 Start camera (with mobile-friendly facingMode)
if (video) {
  navigator.mediaDevices
    .getUserMedia({ video: { facingMode: "user" } })
    .then((stream) => {
      video.srcObject = stream;
    })
    .catch((err) => {
      // Fallback to default camera if facingMode is not supported
      navigator.mediaDevices
        .getUserMedia({ video: true })
        .then((stream) => {
          video.srcObject = stream;
        })
        .catch((err2) => {
          console.error("Camera access denied:", err2);
          alert("Please allow camera access to continue.");
        });
    });
}

// --- Face detection and frame extraction logic ---
async function loadModels() {
  await faceapi.nets.tinyFaceDetector.loadFromUri("/static/models");
}

// Add a progress bar for frame capture
if (!document.getElementById("capture-progress")) {
  const progressBar = document.createElement("div");
  progressBar.id = "capture-progress";
  progressBar.style =
    "width: 100%; height: 8px; background: #eee; margin: 16px 0; display: none;";
  const fill = document.createElement("div");
  fill.id = "capture-progress-fill";
  fill.style =
    "height: 100%; width: 0; background: #4caf50; transition: width 0.1s;";
  progressBar.appendChild(fill);
  document.getElementById("form-section").appendChild(progressBar);
}

function generateUUID() {
  // Simple UUID generator
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, function (c) {
    var r = (Math.random() * 16) | 0,
      v = c == "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

let currentRequestId = null;

async function capture() {
  // Show progress bar
  const progressBar = document.getElementById("capture-progress");
  const fill = document.getElementById("capture-progress-fill");
  progressBar.style.display = "block";
  fill.style.width = "0";

  await loadModels();

  // Generate a new request/session ID
  currentRequestId = generateUUID();

  // Capture as many frames as possible in 5 seconds
  const duration = 5000; // ms
  const start = Date.now();
  const canvas = document.createElement("canvas");
  canvas.width = video.videoWidth;
  canvas.height = video.videoHeight;
  const ctx = canvas.getContext("2d");
  let allFrames = [];
  let frameCount = 0;

  function updateBar() {
    const elapsed = Date.now() - start;
    fill.style.width = Math.min((elapsed / duration) * 100, 100) + "%";
  }

  while (Date.now() - start < duration) {
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const frameData = canvas.toDataURL("image/jpeg", 0.8);
    allFrames.push(frameData);
    frameCount++;
    updateBar();
    await new Promise((r) => setTimeout(r, 20)); // ~50fps max
  }
  progressBar.style.display = "none";

  // Show email input immediately after capture
  showEmailForm();

  // Send frames to backend with request ID (do not wait for email input)
  fetch("/upload_frames", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ frames: allFrames, request_id: currentRequestId }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "no_face") {
        alert("❌ No face found. Try again.");
      } else if (data.status !== "ok") {
        alert("❌ Upload failed: " + (data.message || "Unknown error"));
      }
    })
    .catch((err) => {
      alert("⚠️ Failed to upload frames. Try again.");
      console.error("Upload error:", err);
    });
}

// ✉️ Show email input immediately
function showEmailForm() {
  formSection.innerHTML = `
        <p style="text-align:center; font-size: 18px;">📸 Captured! Enter your email to receive matched images.</p>
        <input type="email" id="userEmail" placeholder="Enter your email" style="margin-top: 20px; padding: 10px; width: 100%; font-size: 16px;" required>
        <button onclick="storeEmail()" class="btn" style="margin-top: 15px;">✅ Confirm Email</button>
    `;
}

// ✅ Store email
function storeEmail() {
  const email = document.getElementById("userEmail").value;
  if (!email || !email.includes("@")) {
    alert("Please enter a valid email.");
    return;
  }

  fetch("/store_email", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email: email, request_id: currentRequestId }),
  })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "ok") {
        requestId = data.request_id;
        localStorage.setItem("request_id", requestId);
        formSection.innerHTML = `
                <p style="text-align:center; font-size: 18px; color: green;">
                    ✅ Email stored. You’ll receive your images once matching is ready.
                </p>
            `;
      } else {
        alert("❌ Failed to store email on server.");
      }
    })
    .catch((err) => {
      console.error("Error storing email:", err);
      alert("⚠️ Could not store email.");
    });
}

// 🔄 Poll until match ready
function pollForResults() {
  requestId = requestId || localStorage.getItem("request_id");
  if (!requestId) {
    alert("No request ID found. Please start the process again.");
    return;
  }
  const interval = setInterval(() => {
    fetch(`/status?request_id=${requestId}`)
      .then((res) => res.json())
      .then((data) => {
        if (data.status === "ready" && storedEmail && !emailSent) {
          clearInterval(interval);
          sendEmailIfStored();
        }
      })
      .catch((err) => {
        console.error("Polling error:", err);
      });
  }, 3000);
}

function clearGallery() {
  if (
    !confirm(
      "⚠️ Are you sure you want to delete all images in the gallery folder?"
    )
  )
    return;

  fetch("/clear_gallery", { method: "POST" })
    .then((res) => res.json())
    .then((data) => {
      if (data.status === "ok") {
        alert("✅ Gallery folder cleared.");
      } else {
        alert("❌ Failed to clear gallery: " + data.message);
      }
    })
    .catch((err) => {
      console.error("Clear gallery error:", err);
      alert("⚠️ An error occurred while clearing the gallery.");
    });
}

// 📤 Send matched images via email
function sendEmailIfStored() {
  if (!storedEmail || emailSent) return;

  emailSent = true;

  fetch("/results")
    .then((res) => res.text())
    .then((html) => {
      const parser = new DOMParser();
      const doc = parser.parseFromString(html, "text/html");
      const checkboxes = doc.querySelectorAll(".image-checkbox");

      const matchedFiles = [];
      checkboxes.forEach((cb) =>
        matchedFiles.push(cb.getAttribute("data-filename"))
      );

      fetch("/send_email", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ images: matchedFiles, email: storedEmail }),
      })
        .then((res) => res.json())
        .then((data) => {
          if (data.status === "ok") {
            formSection.innerHTML = `
                        <p style="text-align:center; font-size: 20px; color: green;">
                            ✅ Images sent to <b>${storedEmail}</b>!
                        </p>
                        <div style="text-align: center; margin-top: 20px;">
                            <button onclick="resetApp()" class="btn">🔁 Try Again</button>
                        </div>
                    `;
            storedEmail = null;
          } else {
            emailSent = false;
            alert("❌ Failed to send email.");
          }
        })
        .catch((err) => {
          emailSent = false;
          console.error("Send email error:", err);
          alert("⚠️ Error sending email.");
        });
    });
}

// 🔁 Reset
function resetApp() {
  localStorage.removeItem("request_id");
  fetch("/reset", { method: "POST" }).then(() => {
    window.location.reload();
  });
}
/* particlesJS.load(@dom-id, @path-json, @callback (optional)); */
particlesJS.load("particles-js", "/static/particles.json", function () {
  console.log("callback - particles.js config loaded");
});
