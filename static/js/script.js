document.addEventListener('DOMContentLoaded', () => {
    const sourceLangSelect = document.getElementById('source-language');
    const targetLangSelect = document.getElementById('target-language');
    const switchBtn = document.getElementById('switch-languages-btn');
    const inputText = document.getElementById('input-text');
    const outputText = document.getElementById('output-text');
    const translationStatus = document.getElementById('translation-status');
    const detectedLanguageInfo = document.getElementById('detected-language-info');
    const inputCharCount = document.getElementById('input-char-count');
    const copyOutputBtn = document.getElementById('copy-output-btn');

    // Menu Elements
    const menuToggle = document.getElementById('menu-toggle');
    const modelMenu = document.getElementById('model-menu');
    const closeMenuButton = document.getElementById('close-menu');
    const menuOverlay = document.getElementById('menu-overlay');
    const availableModelsList = document.getElementById('available-models-list');
    const installedModelsList = document.getElementById('installed-models-list');
    const downloadAllBtn = document.getElementById('download-all-btn'); // Download All button

    // Progress Bar Elements
    const progressContainer = document.getElementById('download-progress-container');
    const progressStatus = document.getElementById('progress-status');
    const progressBar = document.getElementById('progress-bar');
    const progressMessage = document.getElementById('progress-message');

    let currentDownloadCheckInterval = null;
    let translateTimeout = null; // Timer for live translation delay
    const TRANSLATE_DELAY = 750; // Milliseconds delay after user stops typing
    const MAX_INPUT_CHARS = 5000; // Example character limit for textarea

    let currentAvailableModelsCache = []; // Cache for download all feature

    // --- Initial Load ---
    fetchLanguages(); // Load languages for dropdowns
    updateCharCount(); // Initialize char count

    // --- Event Listeners ---

    // Language Switching
    switchBtn.addEventListener('click', switchLanguages);

    // Live Translation on Input
    inputText.addEventListener('input', () => {
        updateCharCount();
        // Clear previous timer
        clearTimeout(translateTimeout);
        // Set a new timer
        translateTimeout = setTimeout(() => {
            triggerTranslation();
        }, TRANSLATE_DELAY);
    });

    // Manual trigger if needed (e.g., after language change)
    sourceLangSelect.addEventListener('change', triggerTranslation);
    targetLangSelect.addEventListener('change', triggerTranslation);

    // Copy output text
    copyOutputBtn.addEventListener('click', copyOutputToClipboard);

    // Menu Handling
    menuToggle.addEventListener('click', openModelMenu);
    closeMenuButton.addEventListener('click', closeMenu);
    menuOverlay.addEventListener('click', closeMenu);

    // Model Actions (Download/Delete) - Use event delegation
    availableModelsList.addEventListener('click', handleModelActionClick);
    installedModelsList.addEventListener('click', handleModelActionClick);

    // Download All Action
    downloadAllBtn.addEventListener('click', handleDownloadAll);

    // --- Core Functions ---

    async function fetchLanguages() {
        try {
            const response = await fetch('/api/languages');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            populateLanguageDropdowns(data.installed);
        } catch (error) {
            console.error("Error fetching languages:", error);
            showStatusMessage("Error loading languages.", true);
        }
    }

    function populateLanguageDropdowns(languages) {
        // Clear existing options except "Auto Detect" for source
        sourceLangSelect.innerHTML = '<option value="auto" selected>Auto Detect</option>';
        targetLangSelect.innerHTML = '';

        if (!languages || languages.length === 0) {
            const defaultOption = '<option value="" disabled selected>No models installed</option>';
            // Don't overwrite Auto Detect
            // sourceLangSelect.innerHTML = defaultOption;
            targetLangSelect.innerHTML = defaultOption;
            showStatusMessage("No translation languages installed. Use the 'Models' menu to download.", true);
            return;
        }

        // Add languages to both selects
        languages.forEach(lang => {
            const option = document.createElement('option');
            option.value = lang.code;
            option.textContent = lang.name;
            // Add to source, but don't select it over "Auto Detect"
            sourceLangSelect.appendChild(option.cloneNode(true));
            targetLangSelect.appendChild(option);
        });

        // Set default target language (e.g., Spanish 'es' if available)
        setDefaultLanguageSelection('es', targetLangSelect);
        // Ensure source defaults to 'auto'
        sourceLangSelect.value = 'auto';
    }

     function setDefaultLanguageSelection(code, selectElement) {
        const optionExists = Array.from(selectElement.options).some(opt => opt.value === code);
        if (optionExists) {
            selectElement.value = code;
        } else if (selectElement.options.length > 0) {
            selectElement.selectedIndex = 0; // Fallback to first available
        }
    }

    function switchLanguages() {
        const sourceVal = sourceLangSelect.value;
        const targetVal = targetLangSelect.value;

        // Avoid switching if source is 'auto' or if values are the same
        if (sourceVal === 'auto' || sourceVal === targetVal) {
            // Optionally provide feedback or just do nothing
             if (sourceVal === 'auto') {
                 showStatusMessage("Cannot switch 'Auto Detect'. Select a specific source language.", true);
                 setTimeout(() => showStatusMessage(""), 3000); // Clear after 3s
             }
            return;
        }

        // Check if the target value exists in the source dropdown options (excluding 'auto')
        const targetInSource = Array.from(sourceLangSelect.options).some(opt => opt.value === targetVal && opt.value !== 'auto');
        // Check if the source value exists in the target dropdown options
        const sourceInTarget = Array.from(targetLangSelect.options).some(opt => opt.value === sourceVal);

        if (targetInSource && sourceInTarget) {
             sourceLangSelect.value = targetVal;
             targetLangSelect.value = sourceVal;
             triggerTranslation(); // Retranslate after switching
        } else {
             showStatusMessage("Cannot switch: Corresponding language model not installed.", true);
             setTimeout(() => showStatusMessage(""), 3000);
        }
        // Clear detected language info on switch
        detectedLanguageInfo.textContent = '';

    }

    function updateCharCount() {
        const currentLength = inputText.value.length;
        inputCharCount.textContent = `${currentLength} / ${MAX_INPUT_CHARS}`;
        if (currentLength > MAX_INPUT_CHARS) {
            inputCharCount.style.color = 'var(--error-color)';
        } else {
            inputCharCount.style.color = 'rgba(255, 255, 255, 0.4)';
        }
    }

    async function triggerTranslation() {
        const text = inputText.value.trim();
        const sourceLang = sourceLangSelect.value;
        const targetLang = targetLangSelect.value;

        // Clear detected language info if not using auto-detect
        if (sourceLang !== 'auto') {
            detectedLanguageInfo.textContent = '';
        }

        if (!text) {
            outputText.value = ""; // Clear output if input is empty
            showStatusMessage(""); // Clear status
            detectedLanguageInfo.textContent = ''; // Clear detected lang
            return;
        }

        if (sourceLang !== 'auto' && sourceLang === targetLang) {
            outputText.value = text; // Just copy if languages are same (and not auto)
            showStatusMessage("Source and target are the same.", false);
             detectedLanguageInfo.textContent = '';
            return;
        }

        if (!targetLang) {
            showStatusMessage("Please select a target language.", true);
            return;
        }

        // Indicate translating (subtly)
        showStatusMessage(""); // Clear previous errors
        outputText.placeholder = "Translating..."; // Use placeholder

        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang })
            });

            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.error || `Translation failed (HTTP ${response.status})`);
            }

            outputText.value = data.translated_text;
            outputText.placeholder = "Translation..."; // Reset placeholder

            // --- Handle Auto-Detect Info (if backend provides it) ---
            if (sourceLang === 'auto' && data.detected_language) {
                 // Assuming backend sends { 'translated_text': '...', 'detected_language': 'English (en)' }
                 detectedLanguageInfo.textContent = `Detected: ${data.detected_language}`;
                 // Make sure the actual source dropdown *isn't* changed
                 sourceLangSelect.value = 'auto';
            } else if (sourceLang === 'auto') {
                 detectedLanguageInfo.textContent = `Detection failed?`; // Or clear it
            }
            // --- End Auto-Detect Handling ---

        } catch (error) {
            console.error("Translation error:", error);
            outputText.value = ""; // Clear output on error
            outputText.placeholder = "Translation failed";
            showStatusMessage(`${error.message}`, true);
            detectedLanguageInfo.textContent = ''; // Clear detected lang on error
        }
    }

     function copyOutputToClipboard() {
        if (!outputText.value) return;
        navigator.clipboard.writeText(outputText.value)
            .then(() => {
                showStatusMessage("Translation copied!", true, 1500); // Use success styling, clear after 1.5s
            })
            .catch(err => {
                console.error('Failed to copy text: ', err);
                showStatusMessage("Failed to copy.", true);
            });
    }

    function showStatusMessage(message, isError = false, clearAfterMs = 0) {
        translationStatus.textContent = message;
        translationStatus.className = 'status-message'; // Reset class
        if (message) {
             translationStatus.classList.add(isError ? 'error' : 'success');
             translationStatus.style.display = 'block';
             if (clearAfterMs > 0) {
                 setTimeout(() => {
                    translationStatus.textContent = '';
                    translationStatus.style.display = 'none';
                 }, clearAfterMs);
             }
        } else {
             translationStatus.style.display = 'none';
        }
    }


    // --- Menu and Model Functions ---

    function openModelMenu() {
        modelMenu.classList.add('open');
        menuOverlay.classList.add('open');
        refreshModelLists(); // Fetch both lists
        updateProgressBar(null); // Reset progress bar
    }

    function closeMenu() {
        modelMenu.classList.remove('open');
        menuOverlay.classList.remove('open');
        stopDownloadStatusCheck();
    }

    function refreshModelListsAndLanguages() {
        fetchLanguages(); // Refresh language dropdowns
        refreshModelLists(); // Refresh model lists in menu
    }

    function refreshModelLists() {
        fetchInstalledModels();
        fetchAvailableModels();
    }

    async function fetchInstalledModels() {
        try {
            const response = await fetch('/api/models/installed');
             if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const installedModels = await response.json();
            displayModels(installedModelsList, installedModels, false);
        } catch (error) {
            console.error("Error fetching installed models:", error);
            installedModelsList.innerHTML = '<p class="error">Error loading installed models.</p>';
        }
    }

    async function fetchAvailableModels() {
        try {
             availableModelsList.innerHTML = '<p>Loading available models...</p>';
            const response = await fetch('/api/models/available');
             if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const availableModels = await response.json();
            currentAvailableModelsCache = availableModels; // Update cache for Download All
            displayModels(availableModelsList, availableModels, true);

        } catch (error) {
            console.error("Error fetching available models:", error);
            currentAvailableModelsCache = []; // Clear cache on error
            availableModelsList.innerHTML = '<p class="error">Error loading available models.</p>';
        }
    }

    function displayModels(listElement, models, isAvailable) {
        listElement.innerHTML = '';
        if (!models || models.length === 0) {
            listElement.innerHTML = `<p>No ${isAvailable ? 'new' : ''} models ${isAvailable ? 'available' : 'installed'}.</p>`;
            return;
        }
        models.forEach(model => {
            const item = document.createElement('div');
            item.classList.add('model-item');
            item.dataset.modelId = model.id;
            item.innerHTML = `
                <div class="model-info">
                    <span>${model.from_name} (${model.from_code}) → ${model.to_name} (${model.to_code})</span>
                    <span class="version">v${model.package_version || 'N/A'} • Argos v${model.argos_version || 'N/A'}</span>
                </div>
                <div class="model-actions">
                    ${isAvailable
                        ? `<button class="model-action-btn download-btn" data-id="${model.id}" data-name="${model.from_name} → ${model.to_name}">Download</button>`
                        : `<button class="model-action-btn delete-btn" data-id="${model.id}" data-name="${model.from_name} → ${model.to_name}">Delete</button>`
                    }
                </div>
            `;
            listElement.appendChild(item);
        });
        // Listeners are handled by delegation on the parent list
    }

    function handleModelActionClick(event) {
         const button = event.target.closest('.model-action-btn');
         if (!button) return;
         const modelId = button.dataset.id;
         const modelName = button.dataset.name;

         if (button.classList.contains('download-btn')) {
             handleDownload(modelId, modelName, button);
         } else if (button.classList.contains('delete-btn')) {
             handleDelete(modelId, modelName, button);
         }
     }

    async function handleDownload(modelId, modelName, button) {
         if (button.disabled) return; // Prevent double clicks while processing
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
             if (!response.ok) throw new Error(data.error || `Server error (HTTP ${response.status})`);

             if (response.status === 202 || response.status === 200) {
                startDownloadStatusCheck(modelId);
                button.textContent = 'Downloading...'; // Update text only on success
             } else {
                  throw new Error(`Unexpected response status: ${response.status}`);
             }
         } catch (error) {
             console.error(`Error initiating download for ${modelId}:`, error);
             updateProgressBar({ status: "error", progress: 0, message: `Start failed: ${error.message}`, id: modelId });
             // Re-enable button immediately on *initiation* failure
             button.disabled = false;
             button.textContent = 'Download';
         }
     }

    async function handleDelete(modelId, modelName, button) {
         if (!confirm(`Are you sure you want to delete model: ${modelName} (${modelId})?`)) return;
         button.disabled = true;
         button.textContent = 'Deleting...';
         try {
             const response = await fetch('/api/models/delete', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ id: modelId })
             });
             const data = await response.json();
             if (!response.ok) throw new Error(data.error || `Server error (HTTP ${response.status})`);
             console.log(`Model ${modelId} deleted successfully.`);
             refreshModelListsAndLanguages(); // Refresh everything
         } catch (error) {
             console.error(`Error deleting model ${modelId}:`, error);
             alert(`Failed to delete model: ${error.message}`);
             button.disabled = false; // Re-enable on error
             button.textContent = 'Delete';
         }
     }

    async function handleDownloadAll() {
        if (currentAvailableModelsCache.length === 0) {
            alert("No available models found to download. Try refreshing the list.");
            return;
        }

        const modelCount = currentAvailableModelsCache.length;
        if (!confirm(`WARNING: This will attempt to queue downloads for all ${modelCount} available models. This may take a very long time and consume significant disk space and bandwidth.\n\nAre you sure you want to proceed?`)) {
            return;
        }

        console.log("Queueing all available models for download...");
        showStatusMessage(`Queueing ${modelCount} models... Check progress below.`, false);

        // Disable the button while queueing
        downloadAllBtn.disabled = true;
        downloadAllBtn.textContent = 'Queueing...';

        let queuedCount = 0;
        for (const model of currentAvailableModelsCache) {
            const modelId = model.id;
            const modelName = `${model.from_name} → ${model.to_name}`;
            // Find the corresponding button in the UI to potentially update its state visually
            const button = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);
            if (button && !button.disabled) {
                 try {
                    // Use the individual download logic, but don't await each one fully
                    await handleDownload(modelId, modelName, button);
                    queuedCount++;
                    // Small delay between requests to avoid overwhelming the server/worker
                    await new Promise(resolve => setTimeout(resolve, 50));
                 } catch (error) {
                     console.error(`Failed to queue ${modelId}: ${error}`);
                     // If queuing fails, re-enable the specific button maybe?
                     if(button) button.disabled = false; button.textContent = 'Download';
                 }
            } else {
                 console.log(`Skipping already queued/disabled model: ${modelId}`);
            }
        }

        // Re-enable the button after queueing is done
        downloadAllBtn.disabled = false;
        downloadAllBtn.textContent = 'Download All Available';
        showStatusMessage(`Finished queueing ${queuedCount} of ${modelCount} models.`, false, 5000); // Clear after 5s
        console.log("Finished queueing all available models.");
        // The first download will start automatically via the worker queue
        // Update the progress bar for the *first* queued item if not already started
        if (queuedCount > 0 && !currentDownloadCheckInterval) {
             const firstModelId = currentAvailableModelsCache.find(m => availableModelsList.querySelector(`.download-btn[data-id="${m.id}"]`)?.textContent === 'Queued')?.id;
             if (firstModelId) {
                 startDownloadStatusCheck(firstModelId);
             }
        }
    }

    // --- Download Progress Polling ---
    function startDownloadStatusCheck(modelId) {
         stopDownloadStatusCheck();
         progressContainer.style.display = 'block';
         const poll = async () => {
            try {
                 const response = await fetch(`/api/download/status/${modelId}`);
                 if (response.status === 404) {
                      console.warn(`Download status 404 for ${modelId}. Stopping poll.`);
                      stopDownloadStatusCheck();
                      updateProgressBar(null); // Clear progress bar
                      // Attempt to refresh lists in case it completed but status was lost
                      refreshModelListsAndLanguages();
                      return;
                 }
                 if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

                 const statusData = await response.json();
                 statusData.id = modelId; // Ensure ID is attached
                 updateProgressBar(statusData); // Update UI

                 if (statusData.status === 'completed' || statusData.status === 'error') {
                     stopDownloadStatusCheck();
                     // Re-enable the specific download button if it exists
                     const btn = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);
                     if (btn) { btn.disabled = false; btn.textContent = 'Download'; }
                     // Refresh lists after completion/error to show changes
                      refreshModelListsAndLanguages();
                      // Optionally hide progress bar after a delay
                     setTimeout(() => updateProgressBar(null), statusData.status === 'completed' ? 5000 : 8000);
                 } else {
                     currentDownloadCheckInterval = setTimeout(poll, 2000); // Poll again
                 }
             } catch (error) {
                 console.error("Error checking download status:", error);
                 updateProgressBar({ status: "error", progress: 0, message: "Error checking status.", id: modelId });
                 stopDownloadStatusCheck();
                 const btn = availableModelsList.querySelector(`.download-btn[data-id="${modelId}"]`);
                 if (btn) { btn.disabled = false; btn.textContent = 'Download'; }
             }
         };
         poll(); // Initial poll
     }

     function stopDownloadStatusCheck() {
         if (currentDownloadCheckInterval) {
             clearTimeout(currentDownloadCheckInterval);
             currentDownloadCheckInterval = null;
         }
     }

     function updateProgressBar(statusData) {
        if (!statusData || !statusData.status || statusData.status === 'not_found') {
             progressContainer.style.display = 'none'; // Hide if no active status
             progressStatus.textContent = "";
             progressMessage.textContent = "";
             progressBar.style.width = '0%';
             progressBar.classList.remove('indeterminate');
             progressMessage.classList.remove('error', 'success');
             return;
         }

         // Ensure container is visible if there's status data
         progressContainer.style.display = 'block';

         progressStatus.textContent = `Status: ${statusData.status.charAt(0).toUpperCase() + statusData.status.slice(1)} (${statusData.id})`; // Show model ID
         progressMessage.textContent = statusData.message || '';
         progressBar.style.width = `${statusData.progress || 0}%`;
         progressMessage.classList.remove('error', 'success');
         progressBar.classList.remove('indeterminate'); // Remove first

         if (statusData.status === 'downloading' || statusData.status === 'installing' || statusData.status === 'queued') {
              // Maybe add indeterminate state for queueing/starting download?
              if (statusData.progress < 5) { // Example threshold
                  progressBar.classList.add('indeterminate');
              }
         }

         if (statusData.status === 'completed') progressMessage.classList.add('success');
         if (statusData.status === 'error') progressMessage.classList.add('error');
    }

}); // End DOMContentLoaded