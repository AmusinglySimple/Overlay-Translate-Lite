document.addEventListener('DOMContentLoaded', () => {
    const sourceLangSelect = document.getElementById('source-language');
    const targetLangSelect = document.getElementById('target-language');
    const inputText = document.getElementById('input-text');
    const outputText = document.getElementById('output-text');
    const translateButton = document.getElementById('translate-button');
    const translationStatus = document.getElementById('translation-status');

    const menuToggle = document.getElementById('menu-toggle');
    const modelMenu = document.getElementById('model-menu');
    const closeMenuButton = document.getElementById('close-menu');
    const menuOverlay = document.getElementById('menu-overlay');
    const availableModelsList = document.getElementById('available-models-list');
    const installedModelsList = document.getElementById('installed-models-list');

    const progressContainer = document.getElementById('download-progress-container');
    const progressStatus = document.getElementById('progress-status');
    const progressBar = document.getElementById('progress-bar');
    const progressMessage = document.getElementById('progress-message');

    let currentDownloadCheckInterval = null;
    // No longer need installedModelsCache for filtering available models
    // let installedModelsCache = [];

    // --- API Fetch Functions ---

    async function fetchLanguages() {
        try {
            const response = await fetch('/api/languages');
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            populateLanguageDropdowns(data.installed);
        } catch (error) {
            console.error("Error fetching languages:", error);
            showStatusMessage("Error loading languages. Please try refreshing.", true);
        }
    }

    async function fetchInstalledModels() {
        try {
            const response = await fetch('/api/models/installed');
             if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const installedModels = await response.json(); // Fetch fresh list
            displayModels(installedModelsList, installedModels, false); // false = not available
        } catch (error) {
            console.error("Error fetching installed models:", error);
            installedModelsList.innerHTML = '<p class="error">Error loading installed models.</p>';
        }
    }

    async function fetchAvailableModels() {
        try {
             // Clear previous content and show loading indicator
             availableModelsList.innerHTML = '<p>Loading available models...</p>';
            const response = await fetch('/api/models/available');
             if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            // Get the list directly from the backend - it should already be filtered.
            const availableModels = await response.json();

            // --- REMOVED THE REDUNDANT FRONTEND FILTERING ---

            // Display the list received from the backend
            displayModels(availableModelsList, availableModels, true); // true = available

        } catch (error) {
            console.error("Error fetching available models:", error);
            availableModelsList.innerHTML = '<p class="error">Error loading available models. Check server logs.</p>';
        }
    }

    // --- UI Update Functions ---

    function populateLanguageDropdowns(languages) {
        sourceLangSelect.innerHTML = ''; // Clear existing
        targetLangSelect.innerHTML = '';

        if (!languages || languages.length === 0) {
            const defaultOption = '<option value="" disabled selected>No languages installed</option>';
            sourceLangSelect.innerHTML = defaultOption;
            targetLangSelect.innerHTML = defaultOption;
             showStatusMessage("No translation languages installed. Use the 'Models' menu to download.", true)
            return;
        }

        languages.forEach(lang => {
            const option = document.createElement('option');
            option.value = lang.code;
            option.textContent = lang.name;
            sourceLangSelect.appendChild(option.cloneNode(true));
            targetLangSelect.appendChild(option);
        });

        // Set default selections (e.g., English to Spanish if available)
        setDefaultLanguageSelection('en', sourceLangSelect);
        setDefaultLanguageSelection('es', targetLangSelect);
    }

     function setDefaultLanguageSelection(code, selectElement) {
        const optionExists = Array.from(selectElement.options).some(opt => opt.value === code);
        if (optionExists) {
            selectElement.value = code;
        } else if (selectElement.options.length > 0) {
            // Fallback to the first available language if the preferred default isn't there
            selectElement.selectedIndex = 0;
        }
    }


    function displayModels(listElement, models, isAvailable) {
        listElement.innerHTML = ''; // Clear existing

        if (!models || models.length === 0) {
            listElement.innerHTML = `<p>No ${isAvailable ? 'new' : ''} models ${isAvailable ? 'available' : 'installed'}.</p>`;
            return;
        }

        models.forEach(model => {
            const item = document.createElement('div');
            item.classList.add('model-item');
            item.dataset.modelId = model.id; // Add data attribute for easier selection if needed

            item.innerHTML = `
                <div class="model-info">
                    <span>${model.from_name} (${model.from_code}) → ${model.to_name} (${model.to_code})</span>
                    <span class="version">v${model.package_version} (Argos ${model.argos_version})</span>
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

        // Add event listeners after elements are added
        addModelActionListeners(listElement);
    }

    function showStatusMessage(message, isError = false) {
        translationStatus.textContent = message;
        translationStatus.className = 'status-message'; // Reset class
        if (message) {
             translationStatus.classList.add(isError ? 'error' : 'success'); // success class isn't used much here, mainly for errors
             translationStatus.style.display = 'block';
        } else {
             translationStatus.style.display = 'none';
        }
    }

    function updateProgressBar(statusData) {
        // Ensure progress container is visible if there's active status
        if (statusData && statusData.status && !['completed', 'error', 'not_found', null].includes(statusData.status)) {
             progressContainer.style.display = 'block';
        } else if (!statusData || ['completed', 'error', 'not_found', null].includes(statusData?.status)) {
             // Optionally hide after a delay for completed/error, or keep visible but idle
            // Consider fading out instead of immediate hide for completed/error
            // For now, let's keep it simple and just update text if hidden/idle needed later.
        }

        if (!statusData || !statusData.status || statusData.status === 'not_found') {
             progressStatus.textContent = "Model Download Status";
             progressMessage.textContent = "Ready to download models.";
             progressBar.style.width = '0%';
             progressBar.classList.remove('indeterminate');
             progressMessage.classList.remove('error', 'success');
             // Optionally hide after a delay: setTimeout(() => progressContainer.style.display = 'none', 3000);
             return;
         }

        progressStatus.textContent = `Status: ${statusData.status.charAt(0).toUpperCase() + statusData.status.slice(1)}`; // Capitalize
        progressMessage.textContent = statusData.message || '';
        progressBar.style.width = `${statusData.progress || 0}%`;
        progressMessage.classList.remove('error', 'success'); // Reset classes first

        if (statusData.status === 'downloading' || statusData.status === 'installing') {
             progressBar.classList.remove('indeterminate'); // Or add if desired
        } else {
             progressBar.classList.remove('indeterminate');
        }

        if (statusData.status === 'completed') {
            progressMessage.classList.add('success');
            // Refresh models lists and languages after completion
            refreshModelListsAndLanguages();
             // Optionally hide progress bar after a delay
             setTimeout(() => {
                 updateProgressBar(null); // Reset to idle state after success message shows
             }, 5000); // Reset after 5 seconds

        } else if (statusData.status === 'error') {
            progressMessage.classList.add('error');
            // Find the button for the errored model in available list (if it exists) and re-enable it
            const errorButton = availableModelsList.querySelector(`.download-btn[data-id="${statusData.id}"]`);
             if (errorButton) {
                 errorButton.disabled = false;
                 errorButton.textContent = 'Download';
             }
             // Optionally hide progress bar after a delay
             setTimeout(() => {
                  updateProgressBar(null); // Reset to idle state after error message shows
             }, 8000); // Keep error visible longer
        }
    }


    // --- Event Handlers ---

    translateButton.addEventListener('click', async () => {
        const text = inputText.value.trim();
        const sourceLang = sourceLangSelect.value;
        const targetLang = targetLangSelect.value;

        if (!text) {
            showStatusMessage("Please enter text to translate.", true);
            return;
        }
        if (!sourceLang || !targetLang) {
             showStatusMessage("Please select source and target languages.", true);
             return;
         }
         if (sourceLang === targetLang) {
             showStatusMessage("Source and target languages cannot be the same.", true);
             outputText.value = text; // Just copy input if languages are same
             return;
         }


        showStatusMessage(""); // Clear previous status
        outputText.value = "Translating...";
        translateButton.disabled = true;

        try {
            const response = await fetch('/api/translate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, source_lang: sourceLang, target_lang: targetLang })
            });

            const data = await response.json();

            if (!response.ok) {
                // Try to parse specific error from backend
                throw new Error(data.error || `Translation failed (HTTP ${response.status})`);
            }

            outputText.value = data.translated_text;

        } catch (error) {
            console.error("Translation error:", error);
            outputText.value = ""; // Clear output on error
            showStatusMessage(`${error.message}`, true);
        } finally {
             translateButton.disabled = false;
        }
    });

    // --- Menu Handling ---
    menuToggle.addEventListener('click', () => {
        modelMenu.classList.add('open');
        menuOverlay.classList.add('open');
         // Refresh lists when opening the menu
         refreshModelLists(); // Fetch both lists
         updateProgressBar(null); // Reset progress bar on open
    });

    closeMenuButton.addEventListener('click', closeMenu);
    menuOverlay.addEventListener('click', closeMenu); // Close when clicking outside

    function closeMenu() {
        modelMenu.classList.remove('open');
        menuOverlay.classList.remove('open');
         // Stop checking download status when menu closes
         stopDownloadStatusCheck();
    }

    // Combined refresh function
    function refreshModelListsAndLanguages() {
        fetchLanguages(); // Refresh language dropdowns
        refreshModelLists(); // Refresh model lists in menu
    }

    // Refresh only model lists (used when menu opens)
    function refreshModelLists() {
        fetchInstalledModels();
        fetchAvailableModels();
    }

    // --- Model Action Handling (Delegated Listeners) ---

    function addModelActionListeners(listElement) {
         // Remove existing listener to prevent duplicates if called multiple times
         listElement.removeEventListener('click', handleModelActionClick);
         // Add the listener
         listElement.addEventListener('click', handleModelActionClick);
     }

     // Separate handler function for clarity
     function handleModelActionClick(event) {
         const button = event.target.closest('.model-action-btn');
         if (!button) return; // Exit if click wasn't on a button

         const modelId = button.dataset.id;
         const modelName = button.dataset.name; // For user feedback

         if (button.classList.contains('download-btn')) {
             handleDownload(modelId, modelName, button);
         } else if (button.classList.contains('delete-btn')) {
             handleDelete(modelId, modelName, button);
         }
     }


     async function handleDownload(modelId, modelName, button) {
         // Optional: Add check if download is already in progress for *this* model
         // if (button.textContent === 'Downloading...' || button.textContent === 'Queued') return;

         // Simple confirm before download
         // if (!confirm(`Download model: ${modelName} (${modelId})?`)) return;

         button.disabled = true;
         button.textContent = 'Queued'; // Update button text immediately
         updateProgressBar({ status: "queued", progress: 0, message: `Queueing ${modelName}...`, id: modelId });

         try {
             const response = await fetch('/api/models/download', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ id: modelId })
             });
             const data = await response.json();

             if (!response.ok) {
                  // Use error from JSON body if available
                 throw new Error(data.error || `Server error (HTTP ${response.status})`);
             }

             // Start polling for status ONLY if request was accepted (202) or OK (200)
             if (response.status === 202 || response.status === 200) {
                startDownloadStatusCheck(modelId);
                // Update button text to show it's actively downloading (poller will update progress bar)
                button.textContent = 'Downloading...';
             } else {
                 // Handle unexpected success codes if necessary
                  throw new Error(`Unexpected response status: ${response.status}`);
             }


         } catch (error) {
             console.error(`Error initiating download for ${modelId}:`, error);
             // Update progress bar with specific error
             updateProgressBar({ status: "error", progress: 0, message: `Start failed: ${error.message}`, id: modelId });
             // Re-enable the button on initiation failure
             button.disabled = false;
             button.textContent = 'Download';
         }
     }

    async function handleDelete(modelId, modelName, button) {
         if (!confirm(`Are you sure you want to delete model: ${modelName} (${modelId})? This cannot be undone.`)) return;

         button.disabled = true;
         button.textContent = 'Deleting...';
         // Optionally remove the item immediately for responsiveness, or wait for confirmation
         // const modelItem = button.closest('.model-item');
         // if(modelItem) modelItem.style.opacity = '0.5';

         try {
             const response = await fetch('/api/models/delete', {
                 method: 'POST',
                 headers: { 'Content-Type': 'application/json' },
                 body: JSON.stringify({ id: modelId })
             });
             const data = await response.json(); // Assume JSON response even for errors

             if (!response.ok) {
                 throw new Error(data.error || `Server error (HTTP ${response.status})`);
             }

             console.log(`Model ${modelId} deleted successfully.`);
              // Refresh lists and languages to show updated state
              refreshModelListsAndLanguages();
             // No need to manually re-enable button, it will be gone after refresh

         } catch (error) {
             console.error(`Error deleting model ${modelId}:`, error);
             alert(`Failed to delete model: ${error.message}`); // Simple alert for deletion error
             // Re-enable button on error
             button.disabled = false;
             button.textContent = 'Delete';
             // if(modelItem) modelItem.style.opacity = '1'; // Restore opacity
         }
     }

     // --- Download Progress Polling ---

     function startDownloadStatusCheck(modelId) {
         stopDownloadStatusCheck(); // Clear any existing interval for other models

         progressContainer.style.display = 'block'; // Show progress area

         // Define the polling function separately
         const poll = async () => {
            try {
                 const response = await fetch(`/api/download/status/${modelId}`);
                 // Assume 404 means it's no longer tracked (could be completed/errored and cleaned up, or invalid)
                 if (response.status === 404) {
                      console.warn(`Download status 404 for ${modelId}. Stopping poll. Refreshing lists.`);
                      stopDownloadStatusCheck();
                      refreshModelListsAndLanguages(); // Refresh to get final state
                      updateProgressBar(null); // Clear progress bar
                      return; // Stop polling
                 }
                 if (!response.ok) {
                     throw new Error(`HTTP error! status: ${response.status}`);
                 }

                 const statusData = await response.json();
                 statusData.id = modelId; // Ensure ID is attached for UI updates
                 updateProgressBar(statusData); // Update UI

                 // Stop polling if download is completed or errored according to status
                 if (statusData.status === 'completed' || statusData.status === 'error') {
                     stopDownloadStatusCheck();
                     // Lists are refreshed inside updateProgressBar for completed/error states now
                 } else {
                     // Schedule the next poll ONLY if not completed/errored
                     currentDownloadCheckInterval = setTimeout(poll, 2000); // Poll again after 2s
                 }

             } catch (error) {
                 console.error("Error checking download status:", error);
                 // Show error in progress bar, attach modelId
                 updateProgressBar({ status: "error", progress: 0, message: "Error checking status.", id: modelId });
                 stopDownloadStatusCheck(); // Stop polling on error
             }
         };

         // Initial poll immediately
         poll();
     }

     function stopDownloadStatusCheck() {
         if (currentDownloadCheckInterval) {
             clearTimeout(currentDownloadCheckInterval); // Use clearTimeout for setTimeout
             currentDownloadCheckInterval = null;
             // console.log("Stopped download status check."); // Less noisy logging
         }
     }


    // --- Initial Load ---
    fetchLanguages(); // Load languages for dropdowns on page load
    // Delay loading models until menu is opened (handled by menu toggle listener)

    // Add initial listeners to list containers (will attach to buttons when they are added)
    addModelActionListeners(availableModelsList);
    addModelActionListeners(installedModelsList);

});