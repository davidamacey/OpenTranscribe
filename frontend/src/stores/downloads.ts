import { writable, get } from "svelte/store";
import { addNotification } from "./notifications";
import { toastStore } from "./toast";
import { t } from "$stores/locale";

export interface DownloadState {
  fileId: string;
  filename: string;
  status: "preparing" | "processing" | "downloading" | "completed" | "error";
  progress?: number;
  startTime: Date;
  error?: string;
  notificationId?: string;
}

function createDownloadStore() {
  const { subscribe, update } = writable<Record<string, DownloadState>>({});

  return {
    subscribe,

    startDownload(fileId: string, filename: string): boolean {
      let canStart = false;

      update((downloads) => {
        // Check if file is already being downloaded
        const existing = downloads[fileId];
        if (
          existing &&
          ["preparing", "processing", "downloading"].includes(existing.status)
        ) {
          toastStore.warning(
            get(t)("downloads.alreadyProcessing", { filename }),
          );
          return downloads;
        }

        canStart = true;

        // Add persistent notification
        addNotification({
          title: get(t)("downloads.videoDownloadStarted"),
          message: get(t)("downloads.preparingWithSubtitles", { filename }),
          type: "info",
          read: false,
          data: { file_id: fileId, download_type: "video_with_subtitles" },
        });

        // Create download state
        downloads[fileId] = {
          fileId,
          filename,
          status: "preparing",
          startTime: new Date(),
        };

        return downloads;
      });

      return canStart;
    },

    updateStatus(
      fileId: string,
      status: DownloadState["status"],
      progress?: number,
      error?: string,
    ) {
      update((downloads) => {
        const download = downloads[fileId];
        if (!download) return downloads;

        download.status = status;
        if (progress !== undefined) download.progress = progress;
        if (error) download.error = error;

        // Update notification based on status
        switch (status) {
          case "processing":
            addNotification({
              title: get(t)("downloads.processingVideo"),
              message: get(t)("downloads.addingSubtitles", {
                filename: download.filename,
              }),
              type: "info",
              read: false,
              data: { file_id: fileId, download_type: "video_processing" },
            });
            break;

          case "downloading":
            addNotification({
              title: get(t)("downloads.processingVideo"),
              message: get(t)("downloads.processingWithSubtitles", {
                filename: download.filename,
              }),
              type: "info",
              read: false,
              data: { file_id: fileId, download_type: "video_ready" },
            });
            break;

          case "completed":
            // Remove from active downloads after a delay
            setTimeout(() => {
              this.removeDownload(fileId);
            }, 30000); // Keep for 30 seconds

            toastStore.success(
              get(t)("downloads.downloadedSuccessfully", {
                filename: download.filename,
              }),
            );
            break;

          case "error":
            addNotification({
              title: get(t)("downloads.downloadFailed"),
              message: get(t)("downloads.failedToProcess", {
                filename: download.filename,
                error: error || get(t)("downloads.unknownError"),
              }),
              type: "error",
              read: false,
              data: { file_id: fileId, download_type: "video_error" },
            });

            toastStore.error(
              get(t)("downloads.downloadFailedError", {
                error: error || get(t)("downloads.unknownError"),
              }),
            );

            // Remove from downloads after error
            setTimeout(() => {
              this.removeDownload(fileId);
            }, 60000); // Keep error for 1 minute
            break;
        }

        return downloads;
      });
    },

    removeDownload(fileId: string) {
      update((downloads) => {
        delete downloads[fileId];
        return downloads;
      });
    },

    isDownloading(fileId: string): boolean {
      let result = false;
      update((downloads) => {
        const download = downloads[fileId];
        result =
          download &&
          ["preparing", "processing", "downloading"].includes(download.status);
        return downloads;
      });
      return result;
    },

    getDownloadStatus(fileId: string): DownloadState | null {
      let result: DownloadState | null = null;
      update((downloads) => {
        result = downloads[fileId] || null;
        return downloads;
      });
      return result;
    },
  };
}

export const downloadStore = createDownloadStore();
