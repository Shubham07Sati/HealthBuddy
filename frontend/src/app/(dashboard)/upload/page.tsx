'use client';

import React, { useState, useRef } from 'react';
import { useRouter } from 'next/navigation';
import { Upload, X, FileText, File, AlertCircle, CheckCircle, Activity, Image as ImageIcon } from 'lucide-react';
import { documentsApi } from '@/lib/api';
import { useAuth } from '@/contexts/AuthContext';

export default function UploadPage() {
  const [files, setFiles] = useState<File[]>([]);
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadError, setUploadError] = useState('');
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { user } = useAuth();

  const handleDragOver = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(true);
  };

  const handleDragLeave = () => {
    setDragging(false);
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragging(false);
    
    if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
      const newFiles = Array.from(e.dataTransfer.files);
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files.length > 0) {
      const newFiles = Array.from(e.target.files);
      setFiles(prev => [...prev, ...newFiles]);
    }
  };

  const removeFile = (index: number) => {
    setFiles(prev => prev.filter((_, i) => i !== index));
  };

  const handleUpload = async () => {
    if (!files.length || !user?.id) return;
    
    setUploading(true);
    setUploadError('');
    
    try {
      const res = await documentsApi.upload(files, user.id);
      // Assuming all files in the batch share a job ID for the pipeline
      if (res.length > 0) {
        setJobId(res[0].document_id); // Use document_id for status polling, not Celery job_id
        setFiles([]); // clear queue on success
      }
    } catch (err: any) {
      setUploadError(err.message || 'Upload failed');
    } finally {
      setUploading(false);
    }
  };

  const getFileIcon = (type: string) => {
    if (type.includes('pdf')) return <FileText className="w-8 h-8 text-red-400" />;
    if (type.includes('image')) return <ImageIcon className="w-8 h-8 text-blue-400" />;
    return <File className="w-8 h-8 text-gray-400" />;
  };

  return (
    <div className="max-w-4xl mx-auto space-y-8 animate-[fadeIn_0.3s_ease-out]">
      <div>
        <h1 className="text-3xl font-bold text-white mb-2">Upload Documents</h1>
        <p className="text-gray-400">Add lab reports, clinical notes, or imaging results to your timeline.</p>
      </div>

      {!jobId ? (
        <div className="space-y-6">
          {/* Dropzone */}
          <div 
            className={`border-2 border-dashed rounded-2xl p-12 text-center transition-all duration-200 ${
              dragging 
                ? 'border-[#4F7CFF] bg-[#4F7CFF]/5 scale-[1.02]' 
                : 'border-slate-700/50 bg-[#111C30]/50 hover:border-slate-600 hover:bg-[#111C30]'
            }`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input 
              type="file" 
              multiple 
              className="hidden" 
              ref={fileInputRef}
              onChange={handleFileChange}
              accept=".pdf,.png,.jpg,.jpeg,.tiff"
            />
            
            <div className="w-20 h-20 mx-auto bg-[#111C30] border border-slate-700/50 rounded-full flex items-center justify-center mb-6 shadow-sm">
              <Upload className={`w-10 h-10 ${dragging ? 'text-[#4F7CFF] animate-bounce' : 'text-slate-400'}`} />
            </div>
            
            <h3 className="text-xl font-semibold text-white mb-2">Click or drag files here to upload</h3>
            <p className="text-gray-400 max-w-sm mx-auto">
              Supported formats: PDF, PNG, JPG, TIFF. Maximum file size: 50MB.
            </p>
          </div>

          {/* File Queue */}
          {files.length > 0 && (
            <div className="bg-[#111C30] border border-slate-700/40 rounded-2xl p-6 shadow-lg">
              <h3 className="text-lg font-medium text-white mb-4">Files to Upload ({files.length})</h3>
              
              <div className="space-y-3 mb-6">
                {files.map((file, index) => (
                  <div key={index} className="flex items-center justify-between p-3 rounded-xl bg-slate-800/30 border border-slate-700/50">
                    <div className="flex items-center space-x-4">
                      <div className="p-2 bg-[rgba(0,0,0,0.2)] rounded-lg">
                        {getFileIcon(file.type)}
                      </div>
                      <div>
                        <p className="text-sm font-medium text-white truncate max-w-[200px] sm:max-w-xs">{file.name}</p>
                        <p className="text-xs text-gray-500">{(file.size / 1024 / 1024).toFixed(2)} MB</p>
                      </div>
                    </div>
                    <button 
                      onClick={(e) => { e.stopPropagation(); removeFile(index); }}
                      className="p-2 text-gray-500 hover:text-red-400 hover:bg-[rgba(239,68,68,0.1)] rounded-lg transition-colors"
                      title="Remove file"
                    >
                      <X className="w-5 h-5" />
                    </button>
                  </div>
                ))}
              </div>

              {uploadError && (
                <div className="mb-4 p-4 rounded-lg bg-[rgba(239,68,68,0.1)] border border-[rgba(239,68,68,0.2)] text-red-400 text-sm flex items-start">
                  <AlertCircle className="w-5 h-5 mr-2 flex-shrink-0 mt-0.5" />
                  <p>{uploadError}</p>
                </div>
              )}

              <div className="flex justify-end">
                <button
                  onClick={handleUpload}
                  disabled={uploading}
                  className="bg-[#4F7CFF] hover:bg-[#3B6EF0] text-white px-8 py-3 rounded-xl font-semibold shadow-lg shadow-[#4F7CFF]/20 transition-all flex items-center disabled:opacity-70 disabled:cursor-not-allowed"
                >
                  {uploading ? (
                    <>
                      <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                        <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                        <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
                      </svg>
                      Uploading...
                    </>
                  ) : (
                    <>
                      <Upload className="w-5 h-5 mr-2" /> Start Processing
                    </>
                  )}
                </button>
              </div>
            </div>
          )}
        </div>
      ) : (
        /* Pipeline Status View */
        <PipelineStatusView jobId={jobId} onReset={() => setJobId(null)} />
      )}
    </div>
  );
}

function PipelineStatusView({ jobId, onReset }: { jobId: string, onReset: () => void }) {
  const router = useRouter();
  const [progress, setProgress] = useState(0);
  const [currentStep, setCurrentStep] = useState(0);
  const [pipelineFailed, setPipelineFailed] = useState(false);
  
  const steps = [
    'Ingestion & Triage',
    'OCR & Layout Extraction',
    'Medical Entity Recognition',
    'Ontology Normalization',
    'Trend Analysis',
    'Reasoning & Insight Generation',
    'Independent Verification'
  ];

  React.useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (jobId) {
      interval = setInterval(async () => {
        try {
          const status = await documentsApi.getStatus(jobId);
          if (status) {
            setProgress(status.progress_percentage || 0);
            const stepIndex = steps.findIndex(s => s === status.current_step);
            if (stepIndex !== -1) {
              setCurrentStep(stepIndex);
            }
            if (status.status === 'complete') {
              setProgress(100);
              setCurrentStep(steps.length);
              clearInterval(interval);
              // Auto-redirect to dashboard after 2.5s so all pages reload with fresh DB data
              setTimeout(() => router.push('/dashboard'), 2500);
            } else if (status.status === 'failed') {
              setPipelineFailed(true);
              clearInterval(interval);
            }
          }
        } catch (e) {
          console.error("Failed to fetch status", e);
        }
      }, 2000);
    }
    return () => clearInterval(interval);
  }, [jobId, steps.length]);

  const isComplete = currentStep >= steps.length;

  return (
    <div className="bg-[#111827] border border-[rgba(255,255,255,0.05)] rounded-2xl p-8 shadow-lg">
      <div className="text-center mb-10">
        <div className="inline-flex items-center justify-center p-4 rounded-full bg-[rgba(59,130,246,0.1)] mb-4 relative">
          {isComplete ? (
            <CheckCircle className="w-12 h-12 text-emerald-400" />
          ) : (
            <>
              <Activity className="w-12 h-12 text-[#3B82F6]" />
              <span className="absolute inset-0 rounded-full border-2 border-[#3B82F6] border-t-transparent animate-spin"></span>
            </>
          )}
        </div>
        <h2 className="text-2xl font-bold text-white mb-2">
          {isComplete ? 'Processing Complete' : 'Analyzing Document'}
        </h2>
        <p className="text-gray-400">
          {isComplete ? 'All data extracted, normalized, and verified.' : 'Our multi-agent pipeline is extracting insights.'}
        </p>
      </div>

      <div className="max-w-md mx-auto mb-10">
        <div className="h-2 bg-[rgba(255,255,255,0.1)] rounded-full overflow-hidden mb-2">
          <div 
            className="h-full bg-gradient-to-r from-[#3B82F6] to-[#10B981] transition-all duration-500 ease-out"
            style={{ width: `${progress}%` }}
          />
        </div>
        <div className="flex justify-between text-xs text-gray-500 font-medium uppercase tracking-wider">
          <span>Processing</span>
          <span>{progress}%</span>
        </div>
      </div>

      <div className="max-w-md mx-auto space-y-0 relative before:absolute before:inset-0 before:ml-5 before:-translate-x-px md:before:mx-auto md:before:translate-x-0 before:h-full before:w-0.5 before:bg-gradient-to-b before:from-transparent before:via-[rgba(255,255,255,0.1)] before:to-transparent">
        {steps.map((step, index) => {
          const isPast = index < currentStep;
          const isCurrent = index === currentStep;
          
          return (
            <div key={index} className="relative flex items-center justify-between md:justify-normal md:odd:flex-row-reverse group is-active py-3">
              <div className="flex items-center justify-center w-10 h-10 rounded-full border-2 border-[rgba(255,255,255,0.1)] bg-[#111827] text-gray-500 shadow shrink-0 md:order-1 md:group-odd:-translate-x-1/2 md:group-even:translate-x-1/2 z-10 transition-colors"
                style={{ 
                  borderColor: isPast ? '#10B981' : isCurrent ? '#3B82F6' : 'rgba(255,255,255,0.1)',
                  color: isPast ? '#10B981' : isCurrent ? '#3B82F6' : 'gray'
                }}
              >
                {isPast ? <CheckCircle className="w-5 h-5" /> : <span className="text-xs font-bold">{index + 1}</span>}
              </div>
              <div className={`w-[calc(100%-4rem)] md:w-[calc(50%-2.5rem)] p-4 rounded-xl border transition-all ${
                isCurrent 
                  ? 'border-[#3B82F6] bg-[rgba(59,130,246,0.05)] shadow-[0_0_15px_rgba(59,130,246,0.1)]' 
                  : isPast
                    ? 'border-[rgba(255,255,255,0.05)] bg-[rgba(255,255,255,0.01)] opacity-70'
                    : 'border-[rgba(255,255,255,0.05)] bg-transparent opacity-40'
              }`}>
                <div className="flex items-center justify-between space-x-2">
                  <div className="font-medium text-white">{step}</div>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {isComplete && (
        <div className="mt-12 flex justify-center space-x-4 animate-[fadeIn_0.5s_ease-out]">
          <button 
            onClick={onReset}
            className="px-6 py-3 rounded-lg border border-[rgba(255,255,255,0.1)] hover:bg-[rgba(255,255,255,0.05)] text-white font-medium transition-colors"
          >
            Upload Another
          </button>
          <button 
            onClick={() => window.location.href = '/dashboard'}
            className="px-6 py-3 rounded-lg bg-[#3B82F6] hover:bg-[#2563EB] text-white font-medium shadow-[0_0_15px_rgba(59,130,246,0.3)] transition-all"
          >
            View Dashboard
          </button>
        </div>
      )}
    </div>
  );
}
