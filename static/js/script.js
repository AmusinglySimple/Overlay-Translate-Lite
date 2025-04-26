document.addEventListener('DOMContentLoaded', () => {
    // --- DOM Elements ---
    const sourceLangSelect = document.getElementById('source-language');
    const targetLangSelect = document.getElementById('target-language');
    const switchBtn = document.getElementById('switch-languages-btn');
    const inputText = document.getElementById('input-text');
    const outputText = document.getElementById('output-text');
    const translationStatus = document.getElementById('translation-status');
    const detectedLanguageInfo = document.getElementById('detected-language-info');
    const inputCharCount = document.getElementById('input-char-count');
    const copyOutputBtn = document.getElementById('copy-output-btn');
    const clearInputBtn = document.getElementById('clear-input-btn');
    const translationLoader = document.getElementById('translation-loader');

    // Menu Elements
    const menuToggle = document.getElementById('menu-toggle');
    const modelMenu = document.getElementById('model-menu');
    const closeMenuButton = document.getElementById('close-menu');
    const menuOverlay = document.getElementById('menu-overlay');
    const availableModelsList = document.getElementById('available-models-list');
    const installedModelsList = document.getElementById('installed-models-list');
    const downloadAllBtn = document.getElementById('download-all-btn');
    const downloadAllStatus = document.getElementById('download-all-status');

    // Progress Bar Elements
    const progressContainer = document.getElementById('download-progress-container');
    const progressStatus = document.getElementById('progress-status');
    const progressBar = document.getElementById('progress-bar');
    const progressMessage = document.getElementById('progress-message');

    // --- State & Config ---
    let currentDownloadCheckInterval = null;
    let translateTimeout = null;
    const TRANSLATE_DELAY = 750; // Milliseconds delay after user stops typing
    const MAX_INPUT_CHARS = window.APP_CONFIG?.MAX_INPUT_CHARS || 5000; // Get from backend/window or default
    let currentAvailableModelsCache = []; // Cache for download all feature
    let isTranslating = false; // Flag to prevent concurrent translation requests

    // --- Initial Load ---
    fetchLanguages(); // Load languages first
    setupEventListeners();
    updateCharCount(); // Initialize char count

    // --- Event Listeners Setup ---
    function setupEventListeners() {
        switchBtn.addEventListener('click', switchLanguages);
        inputText.addEventListener('input', handleInput);
        inputText.addEventListener('keydown', handleInputKeydown); // For Ctrl+Enter
        sourceLangSelect.addEventListener('change', handleLanguageChange);
        targetLangSelect.addEventListener('change', handleLanguageChange);
        copyOutputBtn.addEventListener('click', copyOutputToClipboard);
        clearInputBtn.addEventListener('click', clearInput);
        menuToggle.addEventListener('click', openModelMenu);
        closeMenuButton.addEventListener('click', closeMenu);
        menuOverlay.addEventListener('click', closeMenu);
        availableModelsList.addEventListener('click', handleModelActionClick);
        installedModelsList.addEventListener('click', handleModelActionClick);
        downloadAllBtn.addEventListener('click', handleDownloadAll);
    }

    // --- Core Functions ---

    async function fetchLanguages() {
        try {
            const response = await fetch('/api/languages');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            populateLanguageDropdowns(data.installed);
            loadLanguagePreferences(); // Load preferences *after* populating
            handleIdenticalLanguages(); // Check initial state
        } catch (error) {
            console.error("Error fetching languages:", error);
            showStatusMessage("Error loading languages.", "error");
        }
    }

    function populateLanguageDropdowns(languages) {
        // Clear existing options except "Auto Detect" for source
        const currentSourceVal = sourceLangSelect.value; // Keep if user selected something specific
        const currentTargetVal = targetLangSelect.value;
        sourceLangSelect.innerHTML = '<option value="auto">Auto Detect</option>'; // Set default separate
        targetLangSelect.innerHTML = '';

        if (!languages || languages.length === 0) {
            const defaultOption = '<option value="" disabled>No models installed</option>';
            targetLangSelect.innerHTML = defaultOption;
            sourceLangSelect.appendChild(document.createElement('option')).textContent = "No models installed"; // Add placeholder
            sourceLangSelect.options[1].disabled = true;
            showStatusMessage("No translation models installed. Use the 'Models' menu to download.", "warning");
            return;
        }

        languages.forEach(lang => {
            const option = document.createElement('option');
            option.value = lang.code;
            option.textContent = lang.name;
            sourceLangSelect.appendChild(option.cloneNode(true));
            targetLangSelect.appendChild(option);
        });

        // Try to restore previous selection or set defaults
        if (currentSourceVal && sourceLangSelect.querySelector(`option[value="${currentSourceVal}"]`)) {
             sourceLangSelect.value = currentSourceVal;
        } else {
             sourceLangSelect.value = 'auto'; // Default to auto
        }

         if (currentTargetVal && targetLangSelect.querySelector(`option[value="${currentTargetVal}"]`)) {
            targetLangSelect.value = currentTargetVal;
        } else {
             // Set default target (e.g., 'en' or first available)
             setDefaultLanguageSelection('en', targetLangSelect) || (targetLangSelect.options.length > 0 && (targetLangSelect.selectedIndex = 0));
         }

    }

     function setDefaultLanguageSelection(code, selectElement) {
        const optionExists = Array.from(selectElement.options).some(opt => opt.value === code);
        if (optionExists) {
            selectElement.value = code;
            return true; // Indicate success
        }
        return false; // Indicate failure
    }

    function loadLanguagePreferences() {
        const preferredSource = localStorage.getItem('preferredSourceLang');
        const preferredTarget = localStorage.getItem('preferredTargetLang');

        if (preferredSource && sourceLangSelect.querySelector(`option[value="${preferredSource}"]`)) {
            sourceLangSelect.value = preferredSource;
        }
         // No else needed for source, defaults to 'auto' usually

        if (preferredTarget && targetLangSelect.querySelector(`option[value="${preferredTarget}"]`)) {
            targetLangSelect.value = preferredTarget;
        }
         // No else needed for target, defaults set during population
        console.log("Loaded preferences:", {source: sourceLangSelect.value, target: targetLangSelect.value});
    }

    function saveLanguagePreferences() {
        const sourceVal = sourceLangSelect.value;
        const targetVal = targetLangSelect.value;

        // Only save source if it's not 'auto'
        if (sourceVal && sourceVal !== 'auto') {
            localStorage.setItem('preferredSourceLang', sourceVal);
        } else {
            // Optionally remove preference if set back to auto
            localStorage.removeItem('preferredSourceLang');
        }

        if (targetVal) {
            localStorage.setItem('preferredTargetLang', targetVal);
        }
        console.log("Saved preferences:", {source: sourceVal, target: targetVal});
    }


    function handleLanguageChange() {
        saveLanguagePreferences();
        handleIdenticalLanguages(); // Check if languages are now identical
        triggerTranslation(); // Translate immediately on language change
    }

    function handleIdenticalLanguages() {
        const sourceVal = sourceLangSelect.value;
        const targetVal = targetLangSelect.value;
        const areIdentical = sourceVal !== 'auto' && sourceVal === targetVal;

        sourceLangSelect.classList.toggle('highlight-same-language', areIdentical);
        targetLangSelect.classList.toggle('highlight-same-language', areIdentical);

        if (areIdentical) {
            showStatusMessage("Source and target languages are the same.", "warning", 3000);
            // Optionally disable switch button or give other feedback
        }
    }

    function switchLanguages() {
        const sourceVal = sourceLangSelect.value;
        const targetVal = targetLangSelect.value;

        // Cannot switch if source is 'auto'
        if (sourceVal === 'auto') {
             showStatusMessage("Cannot switch with 'Auto Detect'. Select a specific source language first.", "warning", 3000);
            return;
        }

        // Check if the target value exists as a valid source option (excluding 'auto')
        const targetInSource = sourceLangSelect.querySelector(`option[value="${targetVal}"]:not([value="auto"])`);
        // Check if the source value exists as a valid target option
        const sourceInTarget = targetLangSelect.querySelector(`option[value="${sourceVal}"]`);

        if (targetInSource && sourceInTarget) {
             sourceLangSelect.value = targetVal;
             targetLangSelect.value = sourceVal;
             saveLanguagePreferences(); // Save new preferences
             handleIdenticalLanguages(); // Update highlighting
             triggerTranslation(); // Retranslate
             // Clear detected language info on switch
             detectedLanguageInfo.textContent = '';
        } else {
             showStatusMessage("Cannot switch: The corresponding language model is not installed for both directions.", "error", 4000);
        }
    }

    function handleInput() {
        updateCharCount();
        clearTimeout(translateTimeout);
        translateTimeout = setTimeout(() => {
            triggerTranslation();
        }, TRANSLATE_DELAY);
    }

    function handleInputKeydown(event) {
        // Check for Ctrl+Enter or Cmd+Enter
        if ((event.ctrlKey || event.metaKey) && event.key === 'Enter') {
            event.preventDefault(); // Prevent default action (like adding newline)
            clearTimeout(translateTimeout); // Cancel any pending live translation
            triggerTranslation(); // Trigger immediately
        }
    }

     function clearInput() {
         inputText.value = '';
         outputText.value = '';
         translationStatus.textContent = '';
         translationStatus.style.display = 'none';
         detectedLanguageInfo.textContent = '';
         updateCharCount();
         inputText.focus(); // Focus back on input
     }

    function updateCharCount() {
        const currentLength = inputText.value.length;
        inputCharCount.textContent = `${currentLength} / ${MAX_INPUT_CHARS}`;
        if (currentLength > MAX_INPUT_CHARS) {
            inputCharCount.style.color = 'var(--error-color)';
            inputText.classList.add('error-limit'); // Optional: add class for styling textarea border
        } else {
            inputCharCount.style.color = 'rgba(195, 199, 209, 0.6)';
            inputText.classList.remove('error-limit');
        }
    }

    async function triggerTranslation() {
        if (isTranslating) {
            console.log("Translation already in progress, skipping.");
            return; // Don't start a new request if one is active
        }

        const text = inputText.value.trim();
        const sourceLang = sourceLangSelect.value;
        const targetLang = targetLangSelect.value;

        // Clear detected language info if not using auto-detect
        if (sourceLang !== 'auto') {
            detectedLanguageInfo.textContent = '';
        }
         // Also clear if input is empty
         if (!text) {
              detectedLanguageInfo.textContent = '';
         }


        if (!text) {
            outputText.value = "";
            showStatusMessage("");
            return;
        }

        // Handle identical language selection *before* API call
        if (sourceLang !== 'auto' && sourceLang === targetLang) {
            outputText.value = text;
            showStatusMessage("Source and target languages are the same.", "warning");
            handleIdenticalLanguages(); // Ensure highlighting is correct
            return;
        }

        if (!targetLang) {
            showStatusMessage("Please select a target language.", "error");
            return;
        }

        // Check character limit
        if (text.length > MAX_INPUT_CHARS) {
             showStatusMessage(`Input exceeds maximum length of ${MAX_INPUT_CHARS} characters.`, "error");
             return; // Don't send request if too long
        }


        // Start translation process
        isTranslating = true;
        translationLoader.style.display = 'block'; // Show loader
        showStatusMessage(""); // Clear previous status
        outputText.placeholder = "Translating..."; // Keep placeholder update

        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang })
            });

            const data = await response.json();

            if (!response.ok) {
                 // Use detailed error from backend if available
                const errorMsg = data.message || `Translation failed (HTTP ${response.status})`;
                const errorCode = data.error_code || 'UNKNOWN';
                throw new Error(`[${errorCode}] ${errorMsg}`);
            }

            outputText.value = data.translated_text;
            outputText.placeholder = "Translation"; // Reset placeholder

            // Handle Auto-Detect Info
            if (sourceLang === 'auto') {
                 if (data.detected_language) {
                     detectedLanguageInfo.textContent = `Detected: ${data.detected_language}`;
                 } else {
                      // Backend should ideally send an error if detection failed but proceeded?
                      // Or we indicate uncertainty here.
                      detectedLanguageInfo.textContent = 'Detection uncertain';
                 }
                 // Ensure source dropdown stays on 'auto'
                 sourceLangSelect.value = 'auto';
            }

        } catch (error) {
            console.error("Translation error:", error);
            outputText.value = ""; // Clear output on error
            outputText.placeholder = "Translation failed";
            // Display the error message from the caught error
            showStatusMessage(error.message, "error");
            detectedLanguageInfo.textContent = ''; // Clear detected lang on error
        } finally {
            isTranslating = false;
            translationLoader.style.display = 'none'; // Hide loader
        }
    }

     function copyOutputToClipboard() {
        if (!outputText.value) return;
        navigator.clipboard.writeText(outputText.value)
            .then(() => {
                // Visual feedback
                copyOutputBtn.innerHTML = '✓'; // Change icon to checkmark
                copyOutputBtn.classList.add('copied');
                showStatusMessage("Translation copied!", "success", 1500); // Show success message

                // Revert button after a delay
                setTimeout(() => {
                    copyOutputBtn.innerHTML = '📄'; // Revert icon
                    copyOutputBtn.classList.remove('copied');
                }, 1200); // Slightly shorter than message clear delay
            })
            .catch(err => {
                console.error('Failed to copy text: ', err);
                showStatusMessage("Failed to copy to clipboard.", "error");
            });
    }

    function showStatusMessage(message, type = "info", clearAfterMs = 0) {
        // Clear previous types
        translationStatus.classList.remove('error', 'success', 'warning');
        translationStatus.textContent = message;

        if (message) {
            if (type === 'error') translationStatus.classList.add('error');
            else if (type === 'success') translationStatus.classList.add('success');
            else if (type === 'warning') translationStatus.classList.add('warning');
            // Default is info (no specific class needed beyond base .status-message styling)

            translationStatus.style.display = 'block'; // Make visible

            if (clearAfterMs > 0) {
                 setTimeout(() => {
                    translationStatus.textContent = '';
                    translationStatus.style.display = 'none'; // Hide again
                    translationStatus.classList.remove('error', 'success', 'warning');
                 }, clearAfterMs);
             }
        } else {
             translationStatus.style.display = 'none'; // Hide if message is empty
        }
    }


    // --- Menu and Model Functions ---

    function openModelMenu() {
        modelMenu.classList.add('open');
        menuOverlay.classList.add('open');
        refreshModelLists(); // Fetch both lists
        updateProgressBar(null); // Reset progress bar
        downloadAllStatus.textContent = ''; // Clear download all status
    }

    function closeMenu() {
        modelMenu.classList.remove('open');
        menuOverlay.classList.remove('open');
        stopDownloadStatusCheck(); // Stop polling when menu closes
    }

    // Refreshes models AND language dropdowns
    function refreshModelListsAndLanguages() {
        fetchLanguages(); // Refresh dropdowns (will re-apply prefs)
        refreshModelLists(); // Refresh model lists in menu
    }

    // Refreshes only the model lists in the menu
    function refreshModelLists() {
        fetchInstalledModels();
        fetchAvailableModels();
    }

    async function fetchInstalledModels() {
        try {
            const response = await fetch('/api/models/installed');
             if (!response.ok) {
                 const data = await response.json().catch(() => ({}));
                 throw new Error(data.message || `HTTP error! status: ${response.status}`);
             }
            const installedModels = await response.json();
            displayModels(installedModelsList, installedModels, false);
        } catch (error) {
            console.error("Error fetching installed models:", error);
            installedModelsList.innerHTML = `<p class="error">Error loading installed models: ${error.message}</p>`;
        }
    }

    async function fetchAvailableModels() {
        try {
             availableModelsList.innerHTML = '<p>Loading available models...</p>';
            const response = await fetch('/api/models/available');
             if (!response.ok) {
                 const data = await response.json().catch(() => ({}));
                 throw new Error(data.message || `HTTP error! status: ${response.status}`);
             }
            const availableModels = await response.json();
            currentAvailableModelsCache = availableModels; // Update cache
            displayModels(availableModelsList, availableModels, true);
            // Update Download All button state based on cache
            downloadAllBtn.disabled = currentAvailableModelsCache.length === 0;

        } catch (error) {
            console.error("Error fetching available models:", error);
            currentAvailableModelsCache = []; // Clear cache on error
            availableModelsList.innerHTML = `<p class="error">Error loading available models: ${error.message}</p>`;
            downloadAllBtn.disabled = true; // Disable if loading failed
        }
    }

    function displayModels(listElement, models, isAvailable) {
        listElement.innerHTML = ''; // Clear previous content
        if (!models || models.length === 0) {
            listElement.innerHTML = `<p>No ${isAvailable ? 'new' : ''} models ${isAvailable ? 'available' : 'installed'}.</p>`;
             // Disable Download All if no available models
            if (isAvailable) {
                 downloadAllBtn.disabled = true;
            }
            return;
        }

        // Enable Download All if there are available models
        if (isAvailable) {
             downloadAllBtn.disabled = false;
        }

        models.forEach(model => {
            const item = document.createElement('div');
            item.classList.add('model-item');
            item.dataset.modelId = model.id;

            const modelName = `${model.from_name} (${model.from_code}) → ${model.to_name} (${model.to_code})`;
            const versionInfo = `v${model.package_version || 'N/A'} • Argos v${model.argos_version || 'N/A'}`;
            // --- Package Size Display ---
            // Check if size_mb is provided and format it
            let sizeInfo = '';
            if (model.size_mb !== null && model.size_mb !== undefined) {
                sizeInfo = `<span class="size">(${model.size_mb.toFixed(1)} MB)</span>`;
            } else if (isAvailable) {
                 // Indicate unknown size only for available packages where it might be expected
                 // sizeInfo = `<span class="size">(Size N/A)</span>`; // Optional: be explicit
            }


            item.innerHTML = `
                <div class="model-info">
                    <span>${modelName}</span>
                    <span class="details">${versionInfo} ${sizeInfo}</span>
                </div>
                <div class="model-actions">
                    ${isAvailable
                        ? `<button class="model-action-btn download-btn" data-id="${model.id}" data-name="${modelName}" aria-label="Download ${modelName}">Download</button>`
                        : `<button class="model-action-btn delete-btn" data-id="${model.id}" data-name="${modelName}" aria-label="Delete ${modelName}">Delete</button>`
                    }
                </div>
            `;
            listElement.appendChild(item);
        });
    }

    function handleModelActionClick(event) {
         const button = event.target.closest('.model-action-btn');
         if (!button) return;
         const modelId = button.dataset.id;
         const modelName = button.dataset.name; // For confirmations/messages

         if (button.classList.contains('download-btn')) {
             handleDownload(modelId, modelName, button);
         } else if (button.classList.contains('delete-btn')) {
             handleDelete(modelId, modelName, button);
         }
     }

    async function handleDownload(modelId, modelName, button) {
         if (button.disabled) return;
         button.disabled = true;
         button.textContent = 'Queued';
         updateProgressBar({ status: "queued", progress: 0, message: `Queueing ${modelName}...`, id: modelId });

         try {
             const response = await fetch('/api/models/download', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ id: modelId })
             });
             const data = await response.json();

             // Handle specific errors like "already downloading" (409 Conflict)
             if (response.status === 409) {
                 console.warn(`Model ${modelId} already processing:`, data.message);
                 updateProgressBar({ status: "queued", progress: 0, message: data.message || `Already processing ${modelName}`, id: modelId });
                 button.textContent = 'Processing...'; // Update button text
                 // Optionally start polling status anyway if it was just queued by another client
                 startDownloadStatusCheck(modelId);
                 return; // Don't throw error, just indicate status
             }

             if (!response.ok) {
                 const errorMsg = data.message || `Server error (HTTP ${response.status})`;
                 const errorCode = data.error_code || 'UNKNOWN';
                 throw new Error(`[${errorCode}] ${errorMsg}`);
             }

             // Status 202 Accepted means it's queued
             if (response.status === 202) {
                startDownloadStatusCheck(modelId);
                button.textContent = 'Downloading...';
             } else {
                  // Should ideally not happen if backend returns 202 or error
                  console.warn(`Unexpected success status: ${response.status}`);
                  refreshModelListsAndLanguages(); // Refresh just in case
             }
         } catch (error) {
             console.error(`Error initiating download for ${modelId}:`, error);
             updateProgressBar({ status: "error", progress: 0, message: `Start failed: ${error.message}`, id: modelId });
             // Re-enable button on initiation failure
             button.disabled = false;
             button.textContent = 'Download';
              // Optionally display error near the button too
         }
     }

    async function handleDelete(modelId, modelName, button) {
         if (!confirm(`Are you sure you want to delete model:\n${modelName} (${modelId})?`)) return;
         button.disabled = true;
         button.textContent = 'Deleting...';
         try {
             const response = await fetch('/api/models/delete', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ id: modelId })
             });
             const data = await response.json();
             if (!response.ok) {
                 const errorMsg = data.message || `Server error (HTTP ${response.status})`;
                 const errorCode = data.error_code || 'UNKNOWN';
                 throw new Error(`[${errorCode}] ${errorMsg}`);
             }
             console.log(`Model ${modelId} deleted successfully.`);
             // Refresh everything after successful deletion
             refreshModelListsAndLanguages();
              // Optionally show a success message in the menu for a few seconds
             showTemporaryMenuMessage(`Deleted ${modelName}`, "success");

         } catch (error) {
             console.error(`Error deleting model ${modelId}:`, error);
             alert(`Failed to delete model: ${error.message}`); // Use alert for critical errors like delete failure
             // Re-enable button on error
             button.disabled = false;
             button.textContent = 'Delete';
         }
     }

    async function handleDownloadAll() {
        if (currentAvailableModelsCache.length === 0) {
            alert("No available models found to download. Try refreshing the list.");
            return;
        }

        const modelCount = currentAvailableModelsCache.length;
        // --- Confirmation with Count (Size info pending backend support) ---
        // let confirmationMessage = `WARNING: This will attempt to queue downloads for all ${modelCount} available models.`;
        // TODO: Add size estimation if available from backend later
        // const totalSizeMB = currentAvailableModelsCache.reduce((sum, model) => sum + (model.size_mb || 0), 0);
        // if (totalSizeMB > 0) {
        //     confirmationMessage += `\nEstimated total size: ${totalSizeMB.toFixed(1)} MB.`;
        // }
        // confirmationMessage += "\n\nThis may take a very long time and consume significant disk space and bandwidth.\n\nAre you sure you want to proceed?";
        // Simplified confirmation for now:
        const confirmationMessage = `Queue downloads for all ${modelCount} available models? This may take time and resources.`;


        if (!confirm(confirmationMessage)) {
            return;
        }

        console.log("Queueing all available models for download...");
        downloadAllBtn.disabled = true;
        downloadAllBtn.textContent = 'Queueing (0%)...';
        downloadAllStatus.textContent = `Starting queueing for ${modelCount} models...`;

        let queuedCount = 0;
        let firstModelIdToPoll = null;

        for (let i = 0; i < currentAvailableModelsCache.length; i++) {
            const model = currentAvailableModelsCache[i];
            const modelId = model.id;
            const modelName = `${model.from_name} → ${model.to_name}`;
            const button = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);

            // Update progress text
            const percent = Math.round(((i + 1) / modelCount) * 100);
            downloadAllBtn.textContent = `Queueing (${percent}%)...`;
            downloadAllStatus.textContent = `Queueing ${i + 1} of ${modelCount}: ${modelName}`;


            if (button && !button.disabled) {
                 try {
                    // Call handleDownload but don't necessarily await it fully if we want faster queueing
                    // Awaiting ensures we get immediate feedback on queue initiation failure per model
                    await handleDownload(modelId, modelName, button);

                    // Check if the button text indicates successful queuing or already processing
                    if (button.textContent === 'Downloading...' || button.textContent === 'Processing...') {
                         queuedCount++;
                         if (!firstModelIdToPoll) {
                             firstModelIdToPoll = modelId; // Track the first one successfully queued/started
                         }
                    }
                    // Small delay between requests? Maybe not needed with await.
                    // await new Promise(resolve => setTimeout(resolve, 50));
                 } catch (error) {
                     console.error(`Failed to queue ${modelId}: ${error}`);
                     // Make sure button is re-enabled if queueing failed
                     if(button) { button.disabled = false; button.textContent = 'Download'; }
                 }
            } else {
                 console.log(`Skipping already queued/disabled model: ${modelId}`);
            }
        }

        // Re-enable the button and show final queue status
        downloadAllBtn.disabled = false;
        downloadAllBtn.textContent = 'Download All Available';
        downloadAllStatus.textContent = `Finished queueing ${queuedCount} of ${modelCount} models.`;
        setTimeout(() => { downloadAllStatus.textContent = ''; }, 5000); // Clear status after 5s

        console.log("Finished queueing all available models.");

        // Start polling the status for the *first* model that was successfully queued/started
        if (firstModelIdToPoll && !currentDownloadCheckInterval) {
             startDownloadStatusCheck(firstModelIdToPoll);
        } else if (queuedCount > 0 && currentDownloadCheckInterval) {
             // If polling is already active for another download, it will continue.
             // The worker queue handles processing them sequentially (or concurrently up to max_workers).
             console.log("Download polling already active for another model.");
        }
    }

    // --- Download Progress Polling ---
    function startDownloadStatusCheck(modelId) {
         stopDownloadStatusCheck(); // Ensure only one poller runs
         console.log(`Starting status check for ${modelId}`);
         progressContainer.style.display = 'block'; // Ensure visible

         const poll = async () => {
            // Check if the menu is still open, stop polling if closed
            if (!modelMenu.classList.contains('open')) {
                console.log("Menu closed, stopping status poll.");
                stopDownloadStatusCheck();
                return;
            }

            try {
                 const response = await fetch(`/api/download/status/${modelId}`);

                 // Handle 404 gracefully - means status is gone (completed/error and cleaned up, or never existed)
                 if (response.status === 404) {
                      console.warn(`Download status 404 for ${modelId}. Assuming finished or invalid. Stopping poll.`);
                      stopDownloadStatusCheck();
                      updateProgressBar(null); // Clear progress bar
                      // Refresh lists as the state likely changed
                      refreshModelListsAndLanguages();
                      return;
                 }

                 if (!response.ok) {
                     // Try to get error details from response body
                     const errorData = await response.json().catch(() => ({}));
                     throw new Error(errorData.message || `HTTP error! status: ${response.status}`);
                 }

                 const statusData = await response.json();
                 statusData.id = modelId; // Ensure ID is attached for display
                 updateProgressBar(statusData); // Update UI

                 // Check for terminal states
                 if (statusData.status === 'completed' || statusData.status === 'error') {
                     console.log(`Terminal status ${statusData.status} received for ${modelId}. Stopping poll.`);
                     stopDownloadStatusCheck();
                     // Re-enable the specific download button if it exists and is disabled
                     const btn = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);
                     if (btn && btn.disabled) {
                          btn.disabled = false;
                          btn.textContent = 'Download';
                      }
                     // Refresh lists after completion/error to show changes
                     refreshModelListsAndLanguages();
                     // Hide progress bar after a delay on success/error
                     const hideDelay = statusData.status === 'completed' ? 5000 : 8000;
                     setTimeout(() => {
                         // Only hide if the current progress bar is still showing this model's status
                         if (progressStatus.textContent.includes(`(${modelId})`)) {
                            updateProgressBar(null);
                         }
                     }, hideDelay);

                 } else {
                     // If still processing, schedule the next poll
                     currentDownloadCheckInterval = setTimeout(poll, 2000); // Poll again in 2 seconds
                 }
             } catch (error) {
                 console.error(`Error checking download status for ${modelId}:`, error);
                 // Show error in progress bar area
                 updateProgressBar({ status: "error", progress: 0, message: `Status check failed: ${error.message}`, id: modelId });
                 stopDownloadStatusCheck(); // Stop polling on error
                  // Try to re-enable button
                 const btn = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);
                 if (btn && btn.disabled) { btn.disabled = false; btn.textContent = 'Download'; }
             }
         };
         poll(); // Start the first poll immediately
     }

     function stopDownloadStatusCheck() {
         if (currentDownloadCheckInterval) {
             clearTimeout(currentDownloadCheckInterval);
             currentDownloadCheckInterval = null;
             console.log("Stopped status check interval.");
         }
     }

     function updateProgressBar(statusData) {
        if (!statusData || !statusData.status || statusData.status === 'not_found') {
             // Only hide if no active download seems to be tracked
             // This prevents hiding when switching focus between concurrent downloads quickly
             // Let's keep it visible if *any* download was recently active? Complex.
             // Simplification: Hide if this specific call requests it.
             progressContainer.style.display = 'none';
             progressStatus.textContent = "";
             progressMessage.textContent = "";
             progressBar.style.width = '0%';
             progressBar.classList.remove('indeterminate');
             progressMessage.classList.remove('error', 'success');
             return;
         }

         // Ensure container is visible if there's valid status data
         progressContainer.style.display = 'block';

         // Display status and model ID clearly
         progressStatus.textContent = `Status: ${statusData.status.charAt(0).toUpperCase() + statusData.status.slice(1)} (${statusData.id})`;
         progressMessage.textContent = statusData.message || '';
         progressMessage.classList.remove('error', 'success'); // Clear previous states

         // Update progress bar width
         const progress = statusData.progress || 0;
         progressBar.style.width = `${progress}%`;
         progressBar.classList.remove('indeterminate'); // Assume determinate unless specified

         // Handle specific states
         if (statusData.status === 'queued' || (statusData.status === 'downloading' && progress < 5)) {
              progressBar.classList.add('indeterminate'); // Use indeterminate for queueing/starting
         } else if (statusData.status === 'completed') {
             progressMessage.classList.add('success');
         } else if (statusData.status === 'error') {
             progressMessage.classList.add('error');
         }
    }

    // Helper to show temporary messages in the menu (e.g., after delete)
    function showTemporaryMenuMessage(message, type = "success", duration = 3000) {
         // Could potentially reuse the downloadAllStatus element or add a new one
         downloadAllStatus.textContent = message;
         downloadAllStatus.className = `download-all-queue-status ${type}`; // Reuse class structure maybe
         setTimeout(() => {
            if (downloadAllStatus.textContent === message) { // Avoid clearing unrelated messages
                 downloadAllStatus.textContent = '';
                 downloadAllStatus.className = 'download-all-queue-status';
            }
         }, duration);
    }


}); // End DOMContentLoaded