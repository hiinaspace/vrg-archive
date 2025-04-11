import React from "npm:react";
import DOMPurify from "npm:dompurify";

// thanks to gemini 2.5 for this slop.

// Helper function to format Unix timestamp (seconds)
function formatTimestamp(unixTimestamp) {
  if (!unixTimestamp) return "Invalid Date";
  try {
    const date = new Date(unixTimestamp * 1000);
    // Simple format, adjust as needed (e.g., locale, relative time)
    return date.toLocaleString(); // Example: "4/10/2025, 10:01:10 PM"
  } catch (e) {
    console.error("Error formatting timestamp:", unixTimestamp, e);
    return "Invalid Date";
  }
}

// Helper function to format file size
function formatFileSize(bytes) {
  if (bytes === null || typeof bytes !== "number" || isNaN(bytes) || bytes < 0)
    return "";
  if (bytes === 0) return "0 Bytes";
  const k = 1024;
  const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + " " + sizes[i];
}

function FormatComment({ text }) {
  if (!text) {
    return null;
  }

  let p = DOMPurify.sanitize(text);
  return <span dangerouslySetInnerHTML={{ __html: p }}></span>;
}

// --- The Main Post Component ---
export function Post({ postData }) {
  // Destructure with default values for safety
  const {
    post_num,
    thread_num,
    thread_title = null, // Only present if it's the OP row from the join
    is_op = 0,
    timestamp = null,
    name = "Anonymous",
    trip = null,
    capcode = null,
    comment = "",
    media_filename = null,
    media_w = null,
    media_h = null,
    media_size = null,
    media_hash = null, // MD5 hash
    media_link = null, // Direct link (may need construction)
    thumb_link = null, // Thumbnail link (may need construction)
    media_spoiler = 0, // Treat as boolean/int
  } = postData || {}; // Handle case where postData might be null/undefined

  if (!post_num) {
    return <div className="post error">Error: Invalid post data provided.</div>;
  }

  const isOp = !!is_op; // Convert 0/1 to boolean
  const postClass = `post ${isOp ? "op" : "reply"}`;
  const postId = `p${post_num}`;
  const postInfoId = `pi${post_num}`;
  const messageId = `m${post_num}`;
  const fileId = `f${post_num}`;

  const hasMedia = !!media_filename;

  // Construct media links if they are null but filename/hash exists (example for 4cdn)
  // Adjust logic based on how links were stored or need to be generated
  const effectiveMediaLink =
    media_link || (hasMedia ? `https://i.4cdn.org/vg/${media_filename}` : null); // Example construction
  const effectiveThumbLink =
    thumb_link ||
    (hasMedia
      ? `https://i.4cdn.org/vg/${media_filename.replace(/(\.\w+)$/, "s$1")}`
      : null); // Example construction for 's' thumbnail

  return (
    <div id={postId} className={postClass}>
      {/* Post Info Bar */}
      <div className="postInfo desktop" id={postInfoId}>
        <span className="nameBlock">
          <span className="name">{name}</span>
          {trip && <span className="trip"> {trip}</span>}
          {capcode && capcode !== "N" && (
            <span className="capcode"> ## {capcode}</span>
          )}{" "}
        </span>
        <span
          className="dateTime"
          data-utc={timestamp}
          title={formatTimestamp(timestamp)}
        >
          {formatTimestamp(timestamp)} {/* Display formatted date/time */}
        </span>
        <span className="postNum desktop">
          <a href={`#${postId}`} title="Link to this post">
            No. {post_num}
          </a>
        </span>
      </div>

      {/* File/Media Section */}
      {hasMedia && (
        <div className="file" id={fileId}>
          <div className="fileText">
            File:{" "}
            <a href="/observable.jpg" target="_blank" rel="noopener noreferrer">
              {media_filename}
            </a>
            {" ("}
            {formatFileSize(media_size)}
            {media_w && media_h && `, ${media_w}x${media_h}`}
            {")"}
          </div>
          <a
            className="fileThumb"
            href="/observable.jpg"
            target="_blank"
            rel="noopener noreferrer"
          >
            {/* Basic spoiler handling: maybe blur or hide image based on state */}
            <img
              src="/observable.png"
              alt={formatFileSize(media_size)} // Alt text with file size
              data-md5={media_hash || ""} // Store md5 if available
              style={{ maxWidth: "250px", maxHeight: "250px" }} // Example sizing
              loading="lazy"
            />
          </a>
        </div>
      )}

      {/* Post Message/Comment */}
      <blockquote className="postMessage" id={messageId}>
        <FormatComment text={comment} />
      </blockquote>
    </div>
  );
}
