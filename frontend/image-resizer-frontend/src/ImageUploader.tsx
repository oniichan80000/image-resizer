import React, { useState, ChangeEvent } from 'react';
import axios from 'axios';

// --- Configuration ---
const API_GATEWAY_URL = process.env.REACT_APP_API_GATEWAY_URL;
const DESTINATION_BUCKET_BASE_URL = process.env.REACT_APP_DESTINATION_BUCKET_BASE_URL;

// Type for API response
interface PresignedUrlResponse {
    uploadUrl: string;
    key: string;
}

const ImageUploader: React.FC = () => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadProgress, setUploadProgress] = useState<number>(0);
    const [isUploading, setIsUploading] = useState<boolean>(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [processedImageUrl, setProcessedImageUrl] = useState<string | null>(null);
    const [statusMessage, setStatusMessage] = useState<string>('');

    const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
        if (event.target.files && event.target.files[0]) {
            setSelectedFile(event.target.files[0]);
            setErrorMessage(null);
            setProcessedImageUrl(null);
            setUploadProgress(0);
            setStatusMessage('');
        }
    };

    const handleUpload = async () => {
        if (!selectedFile) {
            setErrorMessage("Please select a file first.");
            return;
        }
        if (!API_GATEWAY_URL || API_GATEWAY_URL === "YOUR_API_GATEWAY_INVOKE_URL"){
             setErrorMessage("Frontend is not configured with API Gateway URL.");
             return;
        }
         if (!DESTINATION_BUCKET_BASE_URL || DESTINATION_BUCKET_BASE_URL.includes("your-destination-bucket-name")){
             setErrorMessage("Frontend is not configured with Destination Bucket URL.");
             return;
        }


        setIsUploading(true);
        setErrorMessage(null);
        setProcessedImageUrl(null);
        setUploadProgress(0);
        setStatusMessage('Getting upload URL...');

        try {
            // 1. Get Presigned URL from our backend API
            const apiEndpoint = `${API_GATEWAY_URL}/generate-upload-url`; // Append resource path
            console.log(`Requesting URL from: ${apiEndpoint}`);
            const response = await axios.post<PresignedUrlResponse>(apiEndpoint, {
                filename: selectedFile.name,
                contentType: selectedFile.type
            });

            const { uploadUrl, key } = response.data;
            console.log("Received presigned URL:", uploadUrl);
            console.log("Object key:", key);

            setStatusMessage('Uploading...');

            // 2. Upload the file directly to S3 using the presigned URL
            await axios.put(uploadUrl, selectedFile, {
                headers: {
                    'Content-Type': selectedFile.type, // Crucial for S3
                },
                onUploadProgress: (progressEvent) => {
                    const percentCompleted = Math.round(
                        (progressEvent.loaded * 100) / (progressEvent.total ?? 1) // Handle potential null total
                    );
                    setUploadProgress(percentCompleted);
                },
            });

            setStatusMessage('Upload successful! Waiting for processing...');
            console.log("File uploaded successfully to S3.");

            // 3. Construct the expected URL for the processed image
            // This assumes the resizing lambda keeps the same key name
            // We add a timestamp query param to help bypass browser cache if replacing image
            const processedUrl = `<span class="math-inline">\{DESTINATION\_BUCKET\_BASE\_URL\}/</span>{key}?t=${Date.now()}`;
            console.log("Expected processed image URL:", processedUrl);

            // Simple approach: Assume processing finishes quickly and set the URL
            // More robust: Poll S3 HeadObject or use WebSocket notifications
            setProcessedImageUrl(processedUrl);
            setStatusMessage('Processing complete (assumed).');


        } catch (error: any) {
            console.error("Upload failed:", error);
            let message = "Upload failed.";
             if (axios.isAxiosError(error)) {
                message = error.response?.data?.message || error.message || message;
             } else if (error instanceof Error) {
                 message = error.message;
             }
            setErrorMessage(message);
            setStatusMessage('');

        } finally {
            setIsUploading(false);
        }
    };

    return (
        <div>
            <h2>Image Resizer Uploader</h2>
            <input type="file" accept="image/*" onChange={handleFileChange} disabled={isUploading} />
            <button onClick={handleUpload} disabled={!selectedFile || isUploading}>
                {isUploading ? `Uploading (${uploadProgress}%)` : "Upload Image"}
            </button>

            {statusMessage && <p>Status: {statusMessage}</p>}
            {errorMessage && <p style={{ color: 'red' }}>Error: {errorMessage}</p>}

            {processedImageUrl && (
                <div>
                    <h3>Processed Image:</h3>
                    <img
                        src={processedImageUrl}
                        alt="Processed"
                        style={{ maxWidth: '300px', maxHeight: '300px', border: '1px solid #ccc' }}
                        // Optional: Add error handling for the image itself
                        onError={(e) => {
                            console.warn("Could not load processed image:", e);
                            setErrorMessage("Processed image not found or still processing. Try refreshing?");
                            setProcessedImageUrl(null); // Clear image on load error
                        }}
                    />
                    <br />
                    <a href={processedImageUrl} download target="_blank" rel="noopener noreferrer">
                        Download Processed Image
                    </a>
                </div>
            )}
        </div>
    );
};

export default ImageUploader;