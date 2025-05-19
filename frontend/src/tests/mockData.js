/**
 * Mock data for testing the FileDetail page and components
 * This provides consistent test data that simulates API responses
 */

// Mock file data with all necessary properties
export const mockFileData = {
  id: 1,
  filename: "test_interview.mp4",
  storage_path: "/uploads/test_interview.mp4",
  upload_time: "2025-05-13T10:30:00Z",
  duration: 120.5,
  language: "en",
  status: "completed",
  summary: "This is a test interview discussing various topics including project management and team collaboration.",
  transcript: {
    segments: [
      {
        id: 1,
        media_file_id: 1,
        start_time: 0,
        end_time: 5.2,
        text: "Hello and welcome to this interview.",
        speaker_id: 1,
        speaker: {
          id: 1,
          name: "Interviewer",
          user_id: 1
        }
      },
      {
        id: 2,
        media_file_id: 1,
        start_time: 5.5,
        end_time: 10.8,
        text: "Thank you for having me today.",
        speaker_id: 2,
        speaker: {
          id: 2,
          name: "Guest",
          user_id: 1
        }
      },
      {
        id: 3,
        media_file_id: 1,
        start_time: 11.2,
        end_time: 20.5,
        text: "Let's start by discussing your background in project management.",
        speaker_id: 1,
        speaker: {
          id: 1,
          name: "Interviewer",
          user_id: 1
        }
      }
    ]
  },
  tags: [
    {
      id: 1,
      name: "interview"
    },
    {
      id: 2,
      name: "project management"
    }
  ],
  user_id: 1
};

// Mock comments data
export const mockComments = [
  {
    id: 1,
    media_file_id: 1,
    user_id: 1,
    text: "This is an important point about project management.",
    timestamp: 12.5,
    created_at: "2025-05-13T11:00:00Z",
    user: {
      id: 1,
      username: "testuser"
    }
  },
  {
    id: 2,
    media_file_id: 1,
    user_id: 2,
    text: "Good question about team collaboration.",
    timestamp: 45.2,
    created_at: "2025-05-13T11:05:00Z",
    user: {
      id: 2,
      username: "admin"
    }
  }
];

// Mock auth store data
export const mockAuthData = {
  isAuthenticated: true,
  user: {
    id: 1,
    username: "testuser",
    email: "test@example.com"
  },
  token: "mock-jwt-token"
};

// Mock blob for media content
export const createMockMediaBlob = () => {
  // Create a simple 1x1 pixel video
  const canvas = document.createElement('canvas');
  canvas.width = 1;
  canvas.height = 1;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = 'black';
  ctx.fillRect(0, 0, 1, 1);
  
  return new Promise(resolve => {
    canvas.toBlob(blob => {
      resolve(blob);
    }, 'video/mp4');
  });
};

// Mock API responses
export const mockApiResponses = {
  getFile: {
    status: 200,
    data: mockFileData
  },
  getComments: {
    status: 200,
    data: mockComments
  },
  addComment: {
    status: 201,
    data: {
      id: 3,
      media_file_id: 1,
      user_id: 1,
      text: "New test comment",
      timestamp: 30.0,
      created_at: "2025-05-13T12:00:00Z"
    }
  },
  getMediaContent: {
    status: 200,
    data: null, // Will be set to blob in tests
    headers: {
      'content-type': 'video/mp4'
    }
  }
};
