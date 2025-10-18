import React, { useState, useCallback } from "react";
import {
  Upload,
  X,
  FileText,
  MapPin,
  TrendingUp,
  AlertCircle,
  Download,
  Play,
  CheckCircle2,
} from "lucide-react";
import { ToastContainer, toast } from "react-toastify";
import "react-toastify/dist/ReactToastify.css";
import { Link } from "react-router-dom";

import "./App.css";

const STBGFrontend = () => {
  const [files, setFiles] = useState({});
  const [processing, setProcessing] = useState(false);
  const [results, setResults] = useState(null);
  const [error, setError] = useState(null);
  const [step, setStep] = useState("upload"); // upload, processing, results

  const requiredFiles = [
    {
      key: "crashes",
      name: "Crashes GeoJSON",
      description: "Historical crash data for safety analysis",
    },
    {
      key: "ej_areas",
      name: "Environmental Justice Areas",
      description: "EJ polygon boundaries (lehd_mpo.geojson)",
    },
    {
      key: "hopewell_frsk",
      name: "Hopewell FRSK",
      description: "Hopewell flood risk data",
    },
    {
      key: "hopewell_fhz",
      name: "Hopewell FHZ",
      description: "Hopewell flood hazard zone data",
    },
    {
      key: "hopewell_wet",
      name: "Hopewell WET",
      description: "Hopewell wetlands data",
    },
    {
      key: "hopewell_con",
      name: "Hopewell CON",
      description: "Hopewell conservation data",
    },
    {
      key: "actv_mpo",
      name: "Activity MPO",
      description: "Activity centers in the MPO",
    },
    {
      key: "t6",
      name: "T6",
      description: "T6 GeoJSON data",
    },
    {
      key: "projects",
      name: "Projects GeoJSON",
      description: "Main project locations with attributes",
    },
    {
      key: "aadt",
      name: "AADT Segments",
      description: "Annual Average Daily Traffic data (stbg_aadt.geojson)",
    },
    {
      key: "pop_emp",
      name: "Population/Employment",
      description:
        "TAZ data with population and employment (pop_emp_df.geojson)",
    },
    {
      key: "non_work_dest",
      name: "Non-Work Destinations",
      description: "Points of interest (grocery, medical, parks, etc.)",
    },
  ];

  const handleFileUpload = useCallback((fileKey, file) => {
    if (file) {
      setFiles((prev) => ({
        ...prev,
        [fileKey]: file,
      }));
    }
  }, []);

  const removeFile = useCallback((fileKey) => {
    setFiles((prev) => {
      const newFiles = { ...prev };
      delete newFiles[fileKey];
      return newFiles;
    });
  }, []);

  const loadSampleFiles = async () => {
    setProcessing(true);
    setError(null);
    try {
      const fileKeys = {
        crashes: "crashes.geojson",
        ej_areas: "lehd_mpo.geojson", // Assuming this is the new EJ areas file
        non_work_dest: "nw.geojson",
        hopewell_frsk: "hopewell_frsk.geojson",
        hopewell_fhz: "hopewell_fhz.geojson",
        hopewell_wet: "hopewell_wet.geojson",
        hopewell_con: "hopewell_con.geojson",
        actv_mpo: "actv_mpo.geojson",
        t6: "t6.geojson",
        projects: "projects.geojson",
        aadt: "stbg_aadt.geojson",
        pop_emp: "pop_emp_df.geojson",
      };

      const filePromises = Object.entries(fileKeys).map(
        async ([key, filename]) => {
          const response = await fetch(`/stbg_elijah/${filename}`);
          if (!response.ok) {
            throw new Error(`Failed to load ${filename}`);
          }
          const blob = await response.blob();
          return [
            key,
            new File([blob], filename, { type: "application/geo+json" }),
          ];
        }
      );

      const fileEntries = await Promise.all(filePromises);
      const newFiles = Object.fromEntries(fileEntries);

      setFiles(newFiles);
      toast.success("Sample data loaded successfully!", {
        position: "top-right",
        autoClose: 3000,
        hideProgressBar: false,
        closeOnClick: true,
        pauseOnHover: true,
        draggable: true,
        progress: undefined,
      });
    } catch (err) {
      setError(`Failed to load sample data: ${err.message}`);
      toast.error(`Failed to load sample data: ${err.message}`, {
        position: "top-right",
        autoClose: 5000,
        hideProgressBar: false,
        closeOnClick: true,
        pauseOnHover: true,
        draggable: true,
        progress: undefined,
      });
    } finally {
      setProcessing(false);
    }
  };

  const processData = async () => {
    setProcessing(true);
    setError(null);
    setStep("processing");
    toast.info("Loading API and processing data...", {
      position: "top-right",
      autoClose: false, // Don't auto close, will be updated on success/error
      hideProgressBar: false,
      closeOnClick: false,
      pauseOnHover: false,
      draggable: true,
      progress: undefined,
      toastId: "processingToast", // Unique ID to update this toast later
    });

    const formData = new FormData();
    formData.append("projects_file", files.projects);
    formData.append("crashes_file", files.crashes);
    formData.append("aadt_file", files.aadt);
    formData.append("pop_emp_file", files.pop_emp);
    formData.append("ej_areas_file", files.ej_areas);
    formData.append("non_work_dest_file", files.non_work_dest);
    formData.append("hopewell_frsk_file", files.hopewell_frsk);
    formData.append("hopewell_fhz_file", files.hopewell_fhz);
    formData.append("hopewell_wet_file", files.hopewell_wet);
    formData.append("hopewell_con_file", files.hopewell_con);
    formData.append("actv_mpo_file", files.actv_mpo);
    formData.append("t6_file", files.t6);

    try {
      const response = await fetch("http://127.0.0.1:8000/analyze", {
        method: "POST",
        body: formData,
      });

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const results = await response.json();
      console.log(results);
      setResults(results);
      setStep("results");
      toast.update("processingToast", {
        render: "API loaded and data processed successfully!",
        type: "success",
        autoClose: 3000,
        hideProgressBar: false,
        closeOnClick: true,
        pauseOnHover: true,
        draggable: true,
        progress: undefined,
      });
    } catch (err) {
      setError("Failed to process data: " + err.message);
      console.error(err);
      setStep("upload");
      toast.update("processingToast", {
        render: `Failed to process data: ${err.message}`,
        type: "error",
        autoClose: 5000,
        hideProgressBar: false,
        closeOnClick: true,
        pauseOnHover: true,
        draggable: true,
        progress: undefined,
      });
    } finally {
      setProcessing(false);
    }
  };

  const downloadResults = () => {
    const dataStr = JSON.stringify(results, null, 2);
    const dataUri =
      "data:application/json;charset=utf-8," + encodeURIComponent(dataStr);
    const exportFileDefaultName = "stbg_results.json";
    const linkElement = document.createElement("a");
    linkElement.setAttribute("href", dataUri);
    linkElement.setAttribute("download", exportFileDefaultName);
    linkElement.click();
  };

  const FileUploadCard = ({ fileInfo }) => {
    const [isDragging, setIsDragging] = useState(false);
    const hasFile = files[fileInfo.key];

    const handleDragOver = useCallback((event) => {
      event.preventDefault();
      setIsDragging(true);
    }, []);

    const handleDragLeave = useCallback(() => {
      setIsDragging(false);
    }, []);

    const handleDrop = useCallback(
      (event) => {
        event.preventDefault();
        setIsDragging(false);
        const droppedFile = event.dataTransfer.files[0];
        if (droppedFile) {
          handleFileUpload(fileInfo.key, droppedFile);
        }
      },
      [fileInfo.key, handleFileUpload]
    );

    const formatBytes = (bytes, decimals = 2) => {
      if (bytes === 0) return "0 Bytes";
      const k = 1024;
      const dm = decimals < 0 ? 0 : decimals;
      const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
      const i = Math.floor(Math.log(bytes) / Math.log(k));
      return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
    };

    return (
      <div
        className={`relative flex flex-col items-center justify-center h-48 p-4 border-2 rounded-lg transition-all duration-300 ease-in-out
          ${
            hasFile
              ? "border-green-500 bg-green-50 shadow-md"
              : isDragging
              ? "border-blue-500 bg-blue-50 shadow-lg"
              : "border-dashed border-gray-300 bg-white hover:border-blue-500 hover:bg-blue-50"
          } cursor-pointer`}
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
      >
        {hasFile ? (
          <div className="flex flex-col items-center space-y-2 text-center">
            <CheckCircle2 className="h-10 w-10 text-green-600" />
            <span className="text-base font-semibold text-green-800 px-2">
              {files[fileInfo.key].name}
            </span>
            <span className="text-sm text-gray-600">
              ({formatBytes(files[fileInfo.key].size)})
            </span>
            <button
              onClick={() => removeFile(fileInfo.key)}
              className="absolute top-2 right-2 text-gray-600 hover:text-red-500 p-1 rounded-full bg-white/70 hover:bg-white focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-opacity-50"
              aria-label="Remove file"
            >
              <X className="h-5 w-5" />
            </button>
          </div>
        ) : (
          <label className="flex flex-col items-center justify-center space-y-2 w-full h-full text-center px-4">
            <Upload
              className={`h-10 w-10 ${
                isDragging ? "text-blue-600" : "text-blue-500"
              }`}
            />
            <span className="text-base font-medium text-gray-700">
              Drag & Drop or{" "}
              <span className="text-blue-600 hover:underline">Browse</span>
            </span>
            <span className="text-sm text-gray-500 mt-1">
              {fileInfo.name}: {fileInfo.description}
            </span>
            <input
              type="file"
              className="hidden"
              accept=".geojson,.json,.shp"
              onChange={(e) =>
                handleFileUpload(fileInfo.key, e.target.files[0])
              }
            />
          </label>
        )}
      </div>
    );
  };

  const ResultsTable = () => (
    <div className="overflow-x-auto shadow ring-1 ring-black ring-opacity-5 sm:rounded-lg">
      <table className="min-w-full divide-y divide-gray-300">
        <thead className="bg-gray-50">
          <tr>
            <th
              scope="col"
              className="py-3.5 pl-4 pr-3 text-left text-sm font-semibold text-gray-900 sm:pl-6"
            >
              Rank
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Project
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Type
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Safety Score
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Congestion Score
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Equity Score
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Benefit
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              Cost (M)
            </th>
            <th
              scope="col"
              className="px-3 py-3.5 text-left text-sm font-semibold text-gray-900"
            >
              BCR
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-200 bg-white">
          {results.projects.map((project) => {
            const safetyScore = project.safety_freq + project.safety_rate;
            const congestionScore = project.cong_demand + project.cong_los;
            const equityScore =
              project.jobs_pc +
              project.jobs_pc_ej +
              project.access_nw_norm +
              project.access_nw_ej_norm;

            return (
              <tr key={project.project_id} className="even:bg-gray-50">
                <td className="whitespace-nowrap py-4 pl-4 pr-3 text-sm font-medium text-gray-900 sm:pl-6">
                  <span
                    className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${
                      project.rank === 1
                        ? "bg-yellow-100 text-yellow-800"
                        : project.rank === 2
                        ? "bg-gray-100 text-gray-800"
                        : "bg-orange-100 text-orange-800"
                    }`}
                  >
                    #{project.rank}
                  </span>
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  Project {project.project_id}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  {project.type}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  {safetyScore.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  {congestionScore.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  {equityScore.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  {project.benefit.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm text-gray-500">
                  ${project.cost_mil.toFixed(1)}
                </td>
                <td className="whitespace-nowrap px-3 py-4 text-sm font-medium text-gray-900">
                  {project.bcr.toFixed(2)}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );

  return (
    <div className="bg-indigo-50">
      <ToastContainer
        position="top-right"
        autoClose={5000}
        hideProgressBar={false}
        newestOnTop={false}
        closeOnClick
        rtl={false}
        pauseOnFocusLoss
        draggable
        pauseOnHover
      />
      <nav className="bg-white shadow-sm p-4 border-b border-indigo-200">
        <div className="max-w-7xl mx-auto flex justify-between items-center">
          <Link to="/" className="flex items-center space-x-2">
            <div>
              {" "}
              <img src="/MPO_Logo.jpg" alt="MPO Logo" className="w-36" />
            </div>
          </Link>
          <h1 className="text-base pt-4 sm:text-lg md:text-xl font-bold text-gray-900">
            Project Prioritization Tool
          </h1>
        </div>
      </nav>
      <div className="flex wrap justify-center mb-8 gap-4 mt-6">
        <button
          onClick={loadSampleFiles}
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-gray-600 hover:bg-gray-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-gray-500"
        >
          Load Sample Data
        </button>
        <button
          onClick={processData}
          disabled={
            Object.keys(files).length < requiredFiles.length || processing
          }
          className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <Play className="w-4 h-4 mr-2" />
          Run Analysis
        </button>

        <button
          onClick={() => {
            setStep("upload");
            setResults(null);
            setFiles({});
          }}
          className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-blue-500"
        >
          Start New Analysis
        </button>
      </div>

      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        {/* Progress Indicator */}
        <div className="flex justify-center mb-8">
          <div className="flex items-center space-x-4">
            <div
              className={`flex items-center ${
                step === "upload" ? "text-blue-600" : "text-green-600"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  step === "upload" ? "bg-blue-100" : "bg-green-100"
                }`}
              >
                {step === "upload" ? (
                  <Upload className="w-4 h-4" />
                ) : (
                  <CheckCircle2 className="w-4 h-4" />
                )}
              </div>
              <span className="ml-2 text-sm font-medium">Upload Data</span>
            </div>
            <div className="w-8 h-0.5 bg-gray-300"></div>
            <div
              className={`flex items-center ${
                step === "processing"
                  ? "text-blue-600"
                  : step === "results"
                  ? "text-green-600"
                  : "text-gray-400"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  step === "processing"
                    ? "bg-blue-100"
                    : step === "results"
                    ? "bg-green-100"
                    : "bg-gray-100"
                }`}
              >
                <TrendingUp className="w-4 h-4" />
              </div>
              <span className="ml-2 text-sm font-medium">Process</span>
            </div>
            <div className="w-8 h-0.5 bg-gray-300"></div>
            <div
              className={`flex items-center ${
                step === "results" ? "text-green-600" : "text-gray-400"
              }`}
            >
              <div
                className={`w-8 h-8 rounded-full flex items-center justify-center ${
                  step === "results" ? "bg-green-100" : "bg-gray-100"
                }`}
              >
                <FileText className="w-4 h-4" />
              </div>
              <span className="ml-2 text-sm font-medium">Results</span>
            </div>
          </div>
        </div>

        {/* Upload Section */}
        {step === "upload" && (
          <div className="bg-white rounded-lg shadow p-6 mb-6">
            <h2 className="text-xl font-semibold text-gray-900 mb-4">
              Upload Required Data Files
            </h2>
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 mb-6">
              {requiredFiles.map((fileInfo) => (
                <FileUploadCard key={fileInfo.key} fileInfo={fileInfo} />
              ))}
            </div>

            {error && (
              <div className="mb-4 p-4 bg-red-50 border border-red-200 rounded-md">
                <div className="flex">
                  <AlertCircle className="h-5 w-5 text-red-400" />
                  <div className="ml-3">
                    <p className="text-sm text-red-800">{error}</p>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* Processing Section */}
        {step === "processing" && (
          <div className="bg-white rounded-lg shadow p-8 text-center">
            <div className="animate-spin rounded-full h-16 w-16 border-b-2 border-blue-600 mx-auto mb-4"></div>
            <h2 className="text-xl font-semibold text-gray-900 mb-2">
              Processing Your Data
            </h2>
            <p className="text-gray-600 mb-4">
              Analyzing safety, congestion, and equity metrics...
            </p>
            <div className="space-y-2 text-sm text-gray-500">
              <p>• Calculating crash frequency and severity scores</p>
              <p>• Analyzing traffic demand and congestion levels</p>
              <p>• Evaluating access to jobs and non-work destinations</p>
              <p>• Computing benefit-cost ratios</p>
            </div>
          </div>
        )}

        {/* Results Section */}
        {step === "results" && results && (
          <div className="space-y-6">
            <div className="bg-white rounded-lg shadow p-6">
              <div className="flex items-center justify-between mb-4">
                <h2 className="text-xl font-semibold text-gray-900">
                  Project Prioritization Results
                </h2>
                <button
                  onClick={downloadResults}
                  className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500"
                >
                  <Download className="w-4 h-4 mr-2" />
                  Export Results
                </button>
              </div>

              <div className="mb-4 grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="bg-blue-50 rounded-lg p-4 text-center">
                  <h3 className="text-lg font-medium text-blue-900">
                    Total Projects
                  </h3>
                  <p className="text-2xl font-bold text-blue-600">
                    {results.projects.length}
                  </p>
                </div>
                <div className="bg-green-50 rounded-lg p-4 text-center">
                  <h3 className="text-lg font-medium text-green-900">
                    Top Ranked BCR
                  </h3>
                  <p className="text-2xl font-bold text-green-600">
                    {results.projects[0]?.bcr.toFixed(2)}
                  </p>
                </div>
                <div className="bg-purple-50 rounded-lg p-4 text-center">
                  <h3 className="text-lg font-medium text-purple-900">
                    Total Cost
                  </h3>
                  <p className="text-2xl font-bold text-purple-600">
                    $
                    {results.projects
                      .reduce((sum, p) => sum + p.cost_mil, 0)
                      .toFixed(1)}
                    M
                  </p>
                </div>
              </div>

              <ResultsTable />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};

export default STBGFrontend;
