import { useEffect, useState } from 'react';
import type { LibraryItem } from '../types';
import { api, rawFileUrl } from '../api';
import { Button, InlineNotice, Modal } from './Common';
import { CheckIcon, ExportIcon, FolderIcon, WarningIcon } from './Icons';

interface WritableFile {
  createWritable: () => Promise<{
    write: (data: Blob) => Promise<void>;
    close: () => Promise<void>;
  }>;
}

interface DirectoryHandle {
  name: string;
  getFileHandle: (name: string, options?: { create?: boolean }) => Promise<WritableFile>;
}

type PickerWindow = Window & {
  showDirectoryPicker?: (options?: { mode?: string }) => Promise<DirectoryHandle>;
};

async function uniqueName(directory: DirectoryHandle, filename: string): Promise<string> {
  const dot = filename.lastIndexOf('.');
  const stem = dot > 0 ? filename.slice(0, dot) : filename;
  const extension = dot > 0 ? filename.slice(dot) : '';
  let candidate = filename;
  let counter = 1;
  while (true) {
    try {
      await directory.getFileHandle(candidate);
      candidate = `${stem} (${counter})${extension}`;
      counter += 1;
    } catch (error) {
      if (error instanceof DOMException && error.name === 'NotFoundError') return candidate;
      throw error;
    }
  }
}

export function ExportDialog({
  open,
  onClose,
  items,
  defaultDestination,
  onNotify,
}: {
  open: boolean;
  onClose: () => void;
  items: LibraryItem[];
  defaultDestination: string;
  onNotify: (message: string, tone?: 'info' | 'success' | 'error') => void;
}) {
  const [destination, setDestination] = useState(defaultDestination);
  const [directoryHandle, setDirectoryHandle] = useState<DirectoryHandle | null>(null);
  const [exporting, setExporting] = useState(false);
  const [results, setResults] = useState<{
    copied: number;
    failed: number;
    destination: string;
    errors: string[];
  } | null>(null);
  const supportsPicker = Boolean((window as PickerWindow).showDirectoryPicker);

  useEffect(() => {
    if (open) {
      setDestination(defaultDestination);
      setDirectoryHandle(null);
      setResults(null);
    }
  }, [open, defaultDestination]);

  const chooseFolder = async () => {
    const picker = (window as PickerWindow).showDirectoryPicker;
    if (!picker) return;
    try {
      const handle = await picker({ mode: 'readwrite' });
      setDirectoryHandle(handle);
      setDestination(handle.name);
      setResults(null);
    } catch (error) {
      if (error instanceof DOMException && error.name === 'AbortError') return;
      onNotify(error instanceof Error ? error.message : 'Could not choose a folder.', 'error');
    }
  };

  const run = async () => {
    if (!items.length) return;
    setExporting(true);
    try {
      if (directoryHandle) {
        const errors: string[] = [];
        let copied = 0;
        for (const item of items) {
          try {
            const response = await fetch(rawFileUrl(item.id));
            if (!response.ok) throw new Error(`Could not read ${item.filename}`);
            const blob = await response.blob();
            const filename = await uniqueName(directoryHandle, item.filename);
            const file = await directoryHandle.getFileHandle(filename, { create: true });
            const writable = await file.createWritable();
            await writable.write(blob);
            await writable.close();
            copied += 1;
          } catch (error) {
            errors.push(`${item.filename}: ${error instanceof Error ? error.message : 'Copy failed'}`);
          }
        }
        setResults({
          copied,
          failed: errors.length,
          destination: directoryHandle.name,
          errors,
        });
        if (errors.length) onNotify(`Copied ${copied}; ${errors.length} failed.`, 'error');
        else onNotify(`Copied ${copied} MIDI file${copied === 1 ? '' : 's'}.`, 'success');
        return;
      }
      const response = await api.exportFiles(items.map((item) => item.id), destination);
      setResults({
        copied: response.copied,
        failed: response.failed,
        destination: response.destination,
        errors: response.results.filter((item) => !item.ok).map((item) => item.error || 'Unknown error'),
      });
      if (response.failed) {
        onNotify(`Copied ${response.copied}; ${response.failed} failed.`, 'error');
      } else {
        onNotify(`Copied ${response.copied} MIDI file${response.copied === 1 ? '' : 's'}.`, 'success');
      }
    } catch (error) {
      onNotify(error instanceof Error ? error.message : 'Could not export files.', 'error');
    } finally {
      setExporting(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={items.length === 1 ? 'Export MIDI file' : `Export ${items.length} MIDI files`}
      eyebrow="Copy original files"
      width="620px"
      footer={
        <>
          <span className="footer-note">Source files are never modified.</span>
          <span className="footer-spacer" />
          <Button onClick={onClose}>{results ? 'Close' : 'Cancel'}</Button>
          <Button variant="primary" icon={<ExportIcon size={14} />} onClick={() => void run()} disabled={exporting || !destination.trim()}>
            {exporting ? 'Copying…' : 'Copy files'}
          </Button>
        </>
      }
    >
      <div className="export-dialog">
        <div className="export-file-list">
          {items.slice(0, 5).map((item) => (
            <div key={item.id} className="export-file-row">
              <span className="export-file-icon">MIDI</span>
              <span className="cell-ellipsis">{item.filename}</span>
              <span className="export-file-folder mono cell-ellipsis">{item.dirname}</span>
            </div>
          ))}
          {items.length > 5 ? <div className="export-more">+{items.length - 5} more files</div> : null}
        </div>
        <div className="export-destination">
          <span className="field-label">Destination folder</span>
          <div className="destination-row">
            <div className="destination-input-wrap">
              <FolderIcon size={15} />
              <input
                className="input"
                value={directoryHandle ? `${directoryHandle.name} — selected in browser` : destination}
                onChange={(event) => setDestination(event.target.value)}
                placeholder="Absolute folder path"
                spellCheck={false}
                disabled={!!directoryHandle}
              />
            </div>
            {supportsPicker ? (
              <Button size="sm" onClick={() => void chooseFolder()}>
                {directoryHandle ? 'Change folder…' : 'Choose folder…'}
              </Button>
            ) : null}
            {directoryHandle ? (
              <button type="button" className="text-action" onClick={() => setDirectoryHandle(null)}>
                use path
              </button>
            ) : null}
          </div>
          <span className="field-hint">
            A new folder is created if needed. Existing files in the destination are not overwritten;
            a numbered filename is used instead. The browser folder picker writes directly to the folder
            you select; otherwise the local service copies to the typed path.
          </span>
        </div>
        <InlineNotice tone="info">
          Exported copies keep the original filename and modification metadata. The indexed original
          is not moved or changed. To drag into a DAW, use the file row or the “drag to DAW” target in
          the details header.
        </InlineNotice>
        {results ? (
          <div className="export-results">
            <div className={`export-result-summary ${results.failed ? 'has-errors' : ''}`}>
              {results.failed ? <WarningIcon size={15} /> : <CheckIcon size={15} />}
              <span>
                {results.copied} copied successfully
                {results.failed ? `, ${results.failed} failed` : ''}
              </span>
            </div>
            <span className="export-result-path mono">{results.destination}</span>
            {results.errors.length ? (
              <ul className="export-error-list">
                {results.errors.map((error, index) => <li key={index}>{error}</li>)}
              </ul>
            ) : null}
          </div>
        ) : null}
      </div>
    </Modal>
  );
}
