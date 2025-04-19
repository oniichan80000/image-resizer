import React, { useState, ChangeEvent, useEffect, useRef } from 'react';
import axios from 'axios';

// --- Configuration ---
const API_GATEWAY_URL = process.env.REACT_APP_API_GATEWAY_URL;
const DESTINATION_BUCKET_BASE_URL = process.env.REACT_APP_DESTINATION_BUCKET_BASE_URL;

// Polling Configuration
const POLL_INTERVAL_MS = 3000; // Check every 3 seconds
const MAX_POLL_ATTEMPTS = 15; // Try up to 15 times (e.g., 45 seconds total)

// Type for API response
interface PresignedUrlResponse {
    uploadUrl: string;
    key: string;
}

interface GetProcessedUrlResponse {
    processedUrl: string;
}

const ImageUploader: React.FC = () => {
    const [selectedFile, setSelectedFile] = useState<File | null>(null);
    const [uploadProgress, setUploadProgress] = useState<number>(0);
    const [isUploading, setIsUploading] = useState<boolean>(false);
    const [errorMessage, setErrorMessage] = useState<string | null>(null);
    const [processedImageUrl, setProcessedImageUrl] = useState<string | null>(null);
    const [statusMessage, setStatusMessage] = useState<string>('');

    // Ref to store the polling interval ID to clear it later
    const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

    // Cleanup polling on component unmount
    useEffect(() => {
        return () => {
            if (pollIntervalRef.current) {
                clearInterval(pollIntervalRef.current);
            }
        };
    }, []);

    const stopPolling = () => {
        if (pollIntervalRef.current) {
            clearInterval(pollIntervalRef.current);
            pollIntervalRef.current = null;
        }
    };

    const pollForProcessedImage = (key: string, attempt: number) => {
        console.log(`Polling for key ${key}, attempt ${attempt}`);
        setStatusMessage(`Processing... (Attempt ${attempt}/${MAX_POLL_ATTEMPTS})`);

        const getUrlEndpoint = `${API_GATEWAY_URL}/get-processed-url?key=${encodeURIComponent(key)}`;

        axios.get<GetProcessedUrlResponse>(getUrlEndpoint)
            .then(response => {
                const secureProcessedUrl = response.data.processedUrl;
                console.log("Polling successful. Received presigned GET URL:", secureProcessedUrl);
                setProcessedImageUrl(secureProcessedUrl);
                setStatusMessage('Processing complete.');
                stopPolling(); // Stop polling on success
            })
            .catch(error => {
                console.warn(`Polling attempt ${attempt} failed:`, error.response?.status, error.message);
                if (attempt >= MAX_POLL_ATTEMPTS) {
                    console.error("Max polling attempts reached.");
                    setErrorMessage("Processing timed out or failed. Please try again.");
                    setStatusMessage('');
                    stopPolling(); // Stop polling on max attempts
                } else if (axios.isAxiosError(error) && error.response?.status !== 404) {
                    // If it's an error other than 404 (Not Found), stop polling and show error
                    setErrorMessage(`Error retrieving processed image: ${error.response?.data?.message || error.message}`);
                    setStatusMessage('');
                    stopPolling();
                }
                // If it's 404, we just let the interval run for the next attempt
            });
    };

    const handleFileChange = (event: ChangeEvent<HTMLInputElement>) => {
        if (event.target.files && event.target.files[0]) {
            setSelectedFile(event.target.files[0]);
            setErrorMessage(null);
            setProcessedImageUrl(null);
            setUploadProgress(0);
            setStatusMessage('');
            stopPolling(); // Stop any previous polling if user selects new file
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
        stopPolling();

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

            setStatusMessage('Upload successful! Getting processed image URL...');
            console.log("File uploaded successfully to S3. Starting polling for key:", key);

            // **** START POLLING ****
            // 3. Poll for the processed image URL
            let attempt = 0;
            // Immediately try once
             pollForProcessedImage(key, ++attempt);
            // Then set interval for subsequent attempts
            pollIntervalRef.current = setInterval(() => {
                pollForProcessedImage(key, ++attempt);
            }, POLL_INTERVAL_MS);
            // **** END POLLING ****


                // 3. Get the Presigned GET URL for the processed image
            try {
                // Construct the URL for the new GET endpoint, passing the key
                const getUrlEndpoint = `<span class="math-inline">\{API\_GATEWAY\_URL\}/get\-processed\-url?key\=</span>{encodeURIComponent(key)}`;
                console.log("Requesting GET URL from:", getUrlEndpoint);

                // Make the GET request
                const getUrlResponse = await axios.get<{ processedUrl: string }>(getUrlEndpoint);
                const secureProcessedUrl = getUrlResponse.data.processedUrl;

                console.log("Received presigned GET URL:", secureProcessedUrl);
                setProcessedImageUrl(secureProcessedUrl); // Use the presigned GET URL
                setStatusMessage('Processing complete.');

            } catch (getUrlError: any) {
                console.error("Failed to get processed image URL:", getUrlError);
                let getMessage = "Could not retrieve processed image URL.";
                if (axios.isAxiosError(getUrlError)) {
                    // Handle 404 specifically if object not found yet
                    if (getUrlError.response?.status === 404) {
                        getMessage = "Processed image not found yet. Try refreshing shortly.";
                    } else {
                        getMessage = getUrlError.response?.data?.message || getUrlError.message || getMessage;
                    }
                } else if (getUrlError instanceof Error) {
                    getMessage = getUrlError.message;
                }
                setErrorMessage(getMessage);
                setStatusMessage('');
            }


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
            setIsUploading(false); // Ensure uploading state is reset on initial error
            stopPolling(); // Stop polling if upload fails
        } finally {
            //setIsUploading(false);
        }
    };

    // When polling succeeds, isUploading should be set to false
    useEffect(() => {
        if (processedImageUrl || errorMessage) {
            setIsUploading(false); // Stop showing upload progress once we have a result or final error
        }
     }, [processedImageUrl, errorMessage]);


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
                    {/* <img
                        src={processedImageUrl}
                        alt="Processed"
                        style={{ maxWidth: '300px', maxHeight: '300px', border: '1px solid #ccc' }}
                        // Optional: Add error handling for the image itself
                        // onError={(e) => {
                        //     console.warn("Could not load processed image:", e);
                        //     setErrorMessage("Processed image not found or still processing. Try refreshing?");
                        //     setProcessedImageUrl(null); // Clear image on load error
                        // }}
                    /> */}
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