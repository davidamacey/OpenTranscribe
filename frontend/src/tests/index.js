/**
 * Test Suite Entry Point
 * 
 * This file exports all test utilities for easy importing
 * and provides a global test runner for the application
 */

import { testFileDetail } from './FileDetailTest';
import { mockFileData, mockComments, mockAuthData } from './mockData';

// Export all test utilities
export {
  testFileDetail,
  mockFileData,
  mockComments,
  mockAuthData
};

// Global test runner
export const runAllTests = async () => {
  console.log('=== Running All Tests ===');
  
  try {
    // Run FileDetail tests
    await testFileDetail();
    
    console.log('=== All Tests Completed Successfully ===');
    return true;
  } catch (error) {
    console.error('=== Test Suite Failed ===');
    console.error(error);
    return false;
  }
};

// Make test runner available globally in development
if (process.env.NODE_ENV !== 'production') {
  window.runTests = runAllTests;
  window.testFileDetail = testFileDetail;
  
  console.log('Test utilities loaded. Run tests with window.runTests() or test specific components with window.testFileDetail()');
}
