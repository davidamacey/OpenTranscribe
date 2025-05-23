<script lang="ts">
  import { onMount } from 'svelte';
  import axios from 'axios';
  
  export let fileId: number | null = null;
  
  let loading = false;
  let error: {message: string; status?: number; data?: any} | null = null;
  let response: {status: number; data: any; headers: any} | null = null;
  let endpointType: 'comments' | 'files' | 'comments-direct' = 'comments';
  let requestUrl = '';
  
  $: if (fileId && endpointType) {
    if (endpointType === 'comments') {
      requestUrl = `/comments/files/${fileId}/comments`;
    } else if (endpointType === 'files') {
      requestUrl = `/files/${fileId}/comments`;
    } else if (endpointType === 'comments-direct') {
      requestUrl = `/comments/files/${fileId}/comments`;
    }
  }
  
  async function testEndpoint() {
    loading = true;
    error = null;
    response = null;
    
    try {
      const token = localStorage.getItem('token');
      const instance = axios.create({
        baseURL: '/api',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': token ? `Bearer ${token}` : ''
        }
      });
      
      console.log(`Testing endpoint: ${requestUrl}`);
      const result = await instance.get(requestUrl);
      response = {
        status: result.status,
        data: result.data,
        headers: result.headers
      };
    } catch (error: unknown) {
      console.error('API Test Error:', error);
      if (error instanceof Error) {
        const axiosError = error as any; // Temporary type assertion for axios error structure
        error = {
          message: error.message,
          status: axiosError.response?.status,
          data: axiosError.response?.data
        };
      } else {
        error = {
          message: 'Unknown error occurred',
          status: undefined,
          data: undefined
        };
      }
    } finally {
      loading = false;
    }
  }
</script>

<div class="debug-panel">
  <h3>API Endpoint Debugger</h3>
  
  <div class="form-group">
    <label for="file-id-input">File ID:</label>
    <input id="file-id-input" type="number" bind:value={fileId} disabled={fileId !== null} />
  </div>
  
  <div class="form-group">
    <label for="endpoint-type">Endpoint Type:</label>
    <select id="endpoint-type" bind:value={endpointType}>
      <option value="comments">/comments/files/{fileId}/comments</option>
      <option value="files">/files/{fileId}/comments</option>
      <option value="comments-direct">/api/comments/files/{fileId}/comments (direct)</option>
    </select>
  </div>
  
  <div class="form-group">
    <label id="request-url-label">Request URL:</label>
    <code aria-labelledby="request-url-label">{requestUrl}</code>
  </div>
  
  <button on:click={testEndpoint} disabled={loading}>
    {#if loading}Testing...{:else}Test Endpoint{/if}
  </button>
  
  {#if response}
    <div class="response success">
      <h4>Response (Status: {response.status})</h4>
      <pre>{JSON.stringify(response.data, null, 2)}</pre>
    </div>
  {/if}
  
  {#if error}
    <div class="response error">
      <h4>Error ({error.status || 'Connection Error'})</h4>
      <pre>{JSON.stringify(error, null, 2)}</pre>
    </div>
  {/if}
</div>

<style>
  .debug-panel {
    background-color: #f5f5f5;
    border: 1px solid #ddd;
    border-radius: 10px;
    padding: 1rem;
    margin: 1rem 0;
    color: #333;
  }
  
  .form-group {
    margin-bottom: 1rem;
  }
  
  label {
    display: block;
    margin-bottom: 0.3rem;
    font-weight: 500;
  }
  
  input, select {
    width: 100%;
    padding: 0.5rem;
    border: 1px solid #ccc;
    border-radius: 4px;
  }
  
  button {
    background-color: #3b82f6;
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    cursor: pointer;
    font-weight: 500;
  }
  
  button:disabled {
    background-color: #94a3b8;
    cursor: not-allowed;
  }
  
  .response {
    margin-top: 1rem;
    padding: 1rem;
    border-radius: 4px;
    overflow: auto;
  }
  
  .success {
    background-color: #ecfdf5;
    border: 1px solid #10b981;
  }
  
  .error {
    background-color: #fef2f2;
    border: 1px solid #ef4444;
  }
  
  pre {
    white-space: pre-wrap;
    word-break: break-all;
    background-color: #f8fafc;
    padding: 0.5rem;
    border-radius: 4px;
    font-size: 0.9rem;
  }
  
  h3 {
    margin-top: 0;
    margin-bottom: 1rem;
  }
  
  h4 {
    margin-top: 0;
    margin-bottom: 0.5rem;
  }
  
  code {
    background-color: #f1f5f9;
    padding: 0.2rem 0.4rem;
    border-radius: 4px;
    font-family: monospace;
  }
</style>
