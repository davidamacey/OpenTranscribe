/**
 * FileDetail Page Test Utility
 * 
 * This utility helps test the FileDetail page functionality by:
 * 1. Mocking API responses
 * 2. Simulating user interactions
 * 3. Verifying expected behavior
 * 
 * Usage: Import this file and call testFileDetail() from the browser console
 */

import { mockFileData, mockComments, mockAuthData, createMockMediaBlob } from './mockData';
import axiosInstance from '../lib/axios';

// Store original axios methods to restore after testing
let originalGet, originalPost;

/**
 * Setup mock API responses for testing
 */
function setupMocks() {
  console.log('[Test] Setting up API mocks for FileDetail testing');
  
  // Store original methods
  originalGet = axiosInstance.get;
  originalPost = axiosInstance.post;
  
  // Mock axios.get to return appropriate test data
  axiosInstance.get = async (url) => {
    console.log(`[Test] Mocked GET request to: ${url}`);
    
    if (url.match(/\/api\/files\/\d+$/)) {
      console.log('[Test] Returning mock file data');
      return { data: mockFileData, status: 200 };
    }
    
    if (url.match(/\/api\/comments\/files\/\d+\/comments$/)) {
      console.log('[Test] Returning mock comments data');
      return { data: mockComments, status: 200 };
    }
    
    if (url.match(/\/api\/files\/\d+\/content$/)) {
      console.log('[Test] Returning mock media blob');
      const blob = await createMockMediaBlob();
      return { 
        data: blob, 
        status: 200, 
        headers: { 'content-type': 'video/mp4' } 
      };
    }
    
    // Default fallback
    console.warn(`[Test] Unhandled GET request to: ${url}`);
    return { data: {}, status: 404 };
  };
  
  // Mock axios.post for comment creation
  axiosInstance.post = async (url, data) => {
    console.log(`[Test] Mocked POST request to: ${url}`, data);
    
    if (url.match(/\/api\/comments\/files\/\d+\/comments$/)) {
      console.log('[Test] Creating mock comment');
      
      // Create a new mock comment with the provided data
      const newComment = {
        id: Math.floor(Math.random() * 1000) + 10, // Random ID
        media_file_id: parseInt(url.match(/\/files\/(\d+)/)[1]),
        user_id: mockAuthData.user.id,
        text: data.text,
        timestamp: data.timestamp,
        created_at: new Date().toISOString(),
        // Include user data to prevent frontend errors
        user: {
          id: mockAuthData.user.id,
          username: mockAuthData.user.username
        }
      };
      
      return { data: newComment, status: 201 };
    }
    
    // Default fallback
    console.warn(`[Test] Unhandled POST request to: ${url}`);
    return { data: {}, status: 404 };
  };
  
  // Setup localStorage mock for auth
  localStorage.setItem('token', 'mock-jwt-token');
  localStorage.setItem('user', JSON.stringify(mockAuthData.user));
  
  console.log('[Test] API mocks setup complete');
}

/**
 * Restore original axios methods after testing
 */
function teardownMocks() {
  console.log('[Test] Tearing down API mocks');
  axiosInstance.get = originalGet;
  axiosInstance.post = originalPost;
  console.log('[Test] Original API methods restored');
}

/**
 * Test the FileDetail page functionality
 */
export async function testFileDetail() {
  console.log('=== FileDetail Page Test ===');
  
  try {
    // Setup mocks
    setupMocks();
    
    // Test steps with verification
    await runTests();
    
    console.log('✅ All FileDetail tests completed successfully!');
  } catch (error) {
    console.error('❌ FileDetail test failed:', error);
  } finally {
    // Clean up
    teardownMocks();
  }
}

/**
 * Run all test steps for the FileDetail page
 */
async function runTests() {
  // Test 1: Verify file data loads correctly
  console.log('[Test] 1. Testing file data loading...');
  const fileDetailElement = document.querySelector('.file-detail');
  if (!fileDetailElement) {
    throw new Error('FileDetail component not found in the DOM');
  }
  
  // Wait for data to load
  await waitForElement('.file-header h1');
  
  // Verify file title is displayed
  const titleElement = document.querySelector('.file-header h1');
  if (!titleElement || titleElement.textContent !== mockFileData.filename) {
    throw new Error(`File title not displayed correctly. Expected: ${mockFileData.filename}, Got: ${titleElement?.textContent}`);
  }
  console.log('✅ File data loaded correctly');
  
  // Test 2: Verify player initialization
  console.log('[Test] 2. Testing media player initialization...');
  const playerElement = document.querySelector('.plyr-player');
  if (!playerElement) {
    throw new Error('Player element not found in the DOM');
  }
  
  // Wait for player to initialize
  await new Promise(resolve => setTimeout(resolve, 1000));
  
  // Check for Plyr controls
  const plyrControls = document.querySelector('.plyr__controls');
  if (!plyrControls) {
    throw new Error('Plyr controls not found - player may not have initialized correctly');
  }
  console.log('✅ Media player initialized correctly');
  
  // Test 3: Verify comments loading
  console.log('[Test] 3. Testing comments loading...');
  
  // Wait for comments to load
  await waitForElement('.comment-item');
  
  // Check if comments are displayed
  const commentItems = document.querySelectorAll('.comment-item');
  if (commentItems.length !== mockComments.length) {
    throw new Error(`Incorrect number of comments displayed. Expected: ${mockComments.length}, Got: ${commentItems.length}`);
  }
  console.log('✅ Comments loaded correctly');
  
  // Test 4: Test adding a new comment
  console.log('[Test] 4. Testing comment creation...');
  
  // Fill in the comment form
  const commentTextarea = document.querySelector('.comment-input textarea');
  const addCommentButton = document.querySelector('.submit-button');
  
  if (!commentTextarea || !addCommentButton) {
    throw new Error('Comment form elements not found');
  }
  
  // Simulate typing a comment
  const testComment = 'This is a test comment from the automated test';
  commentTextarea.value = testComment;
  commentTextarea.dispatchEvent(new Event('input'));
  
  // Click the "Use Current Time" button
  const timeButton = document.querySelector('.timestamp-button');
  if (timeButton) {
    timeButton.click();
    console.log('[Test] Clicked "Mark Current Time" button');
  }
  
  // Submit the comment
  addCommentButton.click();
  console.log('[Test] Submitted new comment');
  
  // Wait for the new comment to appear
  await new Promise(resolve => setTimeout(resolve, 500));
  
  // Verify the new comment was added to the list
  const updatedCommentItems = document.querySelectorAll('.comment-item');
  if (updatedCommentItems.length !== mockComments.length + 1) {
    throw new Error(`New comment was not added. Expected: ${mockComments.length + 1}, Got: ${updatedCommentItems.length}`);
  }
  
  // Check if the new comment text is displayed
  const lastComment = updatedCommentItems[updatedCommentItems.length - 1];
  const commentText = lastComment.querySelector('.comment-body').textContent.trim();
  if (commentText !== testComment) {
    throw new Error(`New comment text doesn't match. Expected: ${testComment}, Got: ${commentText}`);
  }
  
  console.log('✅ Comment creation works correctly');
  
  // Test 5: Verify transcript segments display
  console.log('[Test] 5. Testing transcript segments display...');
  
  // Check if transcript segments are displayed
  const transcriptSegments = document.querySelectorAll('.transcript-segment');
  if (transcriptSegments.length !== mockFileData.transcript.segments.length) {
    throw new Error(`Incorrect number of transcript segments. Expected: ${mockFileData.transcript.segments.length}, Got: ${transcriptSegments.length}`);
  }
  console.log('✅ Transcript segments displayed correctly');
}

/**
 * Helper function to wait for an element to appear in the DOM
 */
function waitForElement(selector, timeout = 5000) {
  console.log(`[Test] Waiting for element: ${selector}`);
  return new Promise((resolve, reject) => {
    if (document.querySelector(selector)) {
      console.log(`[Test] Element already exists: ${selector}`);
      return resolve(document.querySelector(selector));
    }
    
    const observer = new MutationObserver(() => {
      if (document.querySelector(selector)) {
        observer.disconnect();
        console.log(`[Test] Element found: ${selector}`);
        resolve(document.querySelector(selector));
      }
    });
    
    observer.observe(document.body, {
      childList: true,
      subtree: true
    });
    
    setTimeout(() => {
      observer.disconnect();
      reject(new Error(`Timeout waiting for element: ${selector}`));
    }, timeout);
  });
}

// Export test function for use in browser console
window.testFileDetail = testFileDetail;
