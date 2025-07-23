"""
Script for capturing a face from webcam, extracting encodings, and matching against gallery images.
"""
import cv2
import face_recognition
import numpy as np
import os
import shutil
import time

def run_face_matching(reference_frames_dir, gallery_folder):
    """
    Given a directory of reference frames (images), extract face encodings and match against gallery images in the specified gallery_folder.
    Saves matched images to MATCHED_FOLDER as before.
    """
    # --- Config ---
    MATCH_THRESHOLD = 0.45
    MATCHED_FOLDER = "static/matched"

    # --- Prepare matched_faces folder ---
    if os.path.exists(MATCHED_FOLDER):
        shutil.rmtree(MATCHED_FOLDER)
    os.makedirs(MATCHED_FOLDER)

    # --- Step 1: Load Reference Frames ---
    captured_frames = []
    for fname in sorted(os.listdir(reference_frames_dir)):
        if fname.lower().endswith(('.jpg', '.jpeg', '.png')):
            frame = cv2.imread(os.path.join(reference_frames_dir, fname))
            if frame is not None:
                captured_frames.append(frame)
    print(f"✅ Loaded {len(captured_frames)} reference frames from {reference_frames_dir}.")
    if not captured_frames:
        print("❌ No frames found in reference directory.")
        return 0

    # --- Step 2: Extract ALL Face Encodings from Captured Frames ---
    ref_encodings = []
    for frame in captured_frames:
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        faces = face_recognition.face_encodings(rgb)
        ref_encodings.extend(faces)
    if not ref_encodings:
        print("❌ No face detected in reference frames.")
        return 0
    print(f"🧠 Stored {len(ref_encodings)} reference encodings.\n")

    # --- Step 3: Match Against Group Photos ---
    match_count = 0
    for filename in os.listdir(gallery_folder):
        path = os.path.join(gallery_folder, filename)
        img_bgr = cv2.imread(path)
        if img_bgr is None:
            continue
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(img_rgb)
        face_encodings = face_recognition.face_encodings(img_rgb, face_locations)
        matched = False
        for i, enc in enumerate(face_encodings):
            distances = [np.linalg.norm(enc - ref) for ref in ref_encodings]
            min_dist = min(distances)
            if min_dist < MATCH_THRESHOLD:
                matched = True
                top, right, bottom, left = face_locations[i]
                cv2.rectangle(img_bgr, (left, top), (right, bottom), (0, 255, 0), 2)
                cv2.putText(img_bgr, f"{min_dist:.2f}", (left, top - 10),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if matched:
            out_clean_path = os.path.join(MATCHED_FOLDER, f"clean_{filename}")
            cv2.imwrite(out_clean_path, img_rgb[:, :, ::-1])
            out_path = os.path.join(MATCHED_FOLDER, filename)
            cv2.imwrite(out_path, img_bgr)
            match_count += 1
    print(f"\n🎯 {match_count} group image(s) with at least one match saved to '{MATCHED_FOLDER}'.")
    if match_count == 0:
        print("🚫 No perfect matches found.")
    return match_count

# --- Standalone script mode for debugging ---
if __name__ == "__main__":
    # --- Config ---
    FRAME_INTERVAL = 2
    CAPTURE_DURATION = 5
    print("📷 Starting 5-second face capture. Look at the camera...")
    cap = cv2.VideoCapture(0)
    start_time = time.time()
    captured_frames = []
    frame_count = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        elapsed = time.time() - start_time
        if elapsed > CAPTURE_DURATION:
            break
        if frame_count % FRAME_INTERVAL == 0:
            captured_frames.append(frame.copy())
        cv2.imshow("Capturing Face (Look at the Camera)", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
        frame_count += 1
    cap.release()
    cv2.destroyAllWindows()
    cv2.waitKey(1)
    # Save frames to temp dir and run matching
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        for idx, frame in enumerate(captured_frames):
            cv2.imwrite(os.path.join(tmpdir, f'frame_{idx+1:03d}.jpg'), frame)
        run_face_matching(tmpdir, "static/gallery")