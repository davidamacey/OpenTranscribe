# Contributing to OpenTranscribe

Thank you for your interest in contributing to OpenTranscribe! This document provides guidelines and information for contributors.

## 🌟 Ways to Contribute

### 🐛 Bug Reports
- Report bugs using GitHub Issues
- Include detailed reproduction steps
- Provide environment information
- Attach relevant logs and screenshots

### 💡 Feature Requests
- Suggest new features via GitHub Issues
- Provide clear use cases and benefits
- Consider implementation complexity
- Discuss with maintainers before starting work

### 🔧 Code Contributions
- Fix bugs and implement features
- Improve documentation
- Add tests and improve coverage
- Optimize performance

### 📚 Documentation
- Improve existing documentation
- Add examples and tutorials
- Fix typos and clarify instructions
- Translate documentation

## 🚀 Getting Started

### Development Environment Setup

1. **Prerequisites**
   ```bash
   # Required software
   - Docker and Docker Compose
   - Git
   - Node.js (v18+) for frontend development
   - Python (3.11+) for backend development
   
   # Recommended
   - NVIDIA GPU with CUDA support (for AI processing)
   - 16GB+ RAM (for large models)
   - Visual Studio Code with recommended extensions
   ```

2. **Fork and Clone**
   ```bash
   # Fork the repository on GitHub
   # Clone your fork
   git clone https://github.com/yourusername/OpenTranscribe.git
   cd OpenTranscribe
   
   # Add upstream remote
   git remote add upstream https://github.com/original/OpenTranscribe.git
   ```

3. **Environment Setup**
   ```bash
   # Make utility script executable
   chmod +x opentr.sh
   
   # Copy environment template
   cp .env.example .env
   # Edit .env with your settings if needed
   
   # Start development environment
   ./opentr.sh start dev
   ```

4. **Verify Setup**
   ```bash
   # Check all services are running
   ./opentr.sh status
   
   # Access the application
   # Frontend: http://localhost:5173
   # API: http://localhost:8080/docs
   # Flower: http://localhost:5555/flower
   ```

## 🏗️ Development Workflow

### Branch Strategy
```bash
# Create feature branch from main
git checkout main
git pull upstream main
git checkout -b feature/your-feature-name

# For bug fixes
git checkout -b fix/issue-description

# For documentation
git checkout -b docs/improvement-description
```

### Making Changes

#### Backend Development
```bash
# Navigate to backend
cd backend/

# Install dependencies (if developing outside Docker)
pip install -r requirements.txt

# Run tests
./opentr.sh shell backend
pytest tests/

# Code style
black app/
isort app/
flake8 app/
```

#### Frontend Development
```bash
# Navigate to frontend
cd frontend/

# Install dependencies
npm install

# Run tests
npm run test

# Code style
npm run lint
npm run format

# Type checking
npm run check
```

### Testing Requirements

#### Backend Tests
- **Unit Tests**: Test individual functions and classes
- **Integration Tests**: Test API endpoints and database operations
- **Service Tests**: Test business logic and external integrations

```bash
# Run all tests
pytest tests/

# Run specific test file
pytest tests/api/endpoints/test_files.py

# Run with coverage
pytest --cov=app tests/

# Run only fast tests (exclude integration)
pytest -m "not integration" tests/
```

#### Frontend Tests
- **Component Tests**: Test individual Svelte components
- **Store Tests**: Test state management
- **Integration Tests**: Test user workflows

```bash
# Run unit tests
npm run test

# Run component tests
npm run test:components

# Run E2E tests
npm run test:e2e

# Watch mode
npm run test:watch
```

### Code Quality Standards

#### Python (Backend)
```python
# Type hints required
def process_file(file_id: int, user: User) -> ProcessResult:
    """Process a file with proper type hints."""
    pass

# Google-style docstrings
def transcribe_audio(audio_path: str) -> Dict[str, Any]:
    """
    Transcribe audio file using WhisperX.
    
    Args:
        audio_path: Path to the audio file
        
    Returns:
        Dictionary containing transcription results
        
    Raises:
        TranscriptionError: If transcription fails
    """
    pass

# Error handling
try:
    result = risky_operation()
except SpecificError as e:
    logger.error(f"Operation failed: {e}")
    raise ErrorHandler.processing_error("operation", e)
```

#### TypeScript (Frontend)
```typescript
// Interfaces for all data structures
interface User {
  id: number;
  email: string;
  is_superuser: boolean;
}

// Proper component props
interface FileUploaderProps {
  onUpload: (file: File) => void;
  acceptedTypes: string[];
  maxSize: number;
}

// Error handling
try {
  const response = await api.uploadFile(file);
  addNotification({ type: 'success', message: 'File uploaded' });
} catch (error) {
  addNotification({ type: 'error', message: error.message });
}
```

#### CSS (Frontend)
```css
/* Use CSS variables for theming */
.component {
  background-color: var(--background-color);
  color: var(--text-color);
  border: 1px solid var(--border-color);
}

/* Mobile-first responsive design */
.container {
  width: 100%;
  padding: 1rem;
}

@media (min-width: 768px) {
  .container {
    padding: 2rem;
  }
}

/* Semantic class names */
.file-upload-zone {
  /* Not .blue-box */
}
```

## 📋 Pull Request Process

### Before Submitting
1. **Update Documentation**
   - Update relevant README files
   - Add docstrings and comments
   - Update API documentation if needed

2. **Test Your Changes**
   - Run full test suite
   - Test manually in browser
   - Verify no regressions

3. **Code Quality**
   - Follow coding standards
   - Run linting and formatting
   - Fix any warnings or errors

### Pull Request Template
```markdown
## Description
Brief description of the changes

## Type of Change
- [ ] Bug fix (non-breaking change that fixes an issue)
- [ ] New feature (non-breaking change that adds functionality)
- [ ] Breaking change (fix or feature that causes existing functionality to not work as expected)
- [ ] Documentation update

## Testing
- [ ] I have added tests that prove my fix is effective or that my feature works
- [ ] New and existing unit tests pass locally with my changes
- [ ] I have tested this manually

## Screenshots (if applicable)
Add screenshots to help explain your changes

## Checklist
- [ ] My code follows the style guidelines of this project
- [ ] I have performed a self-review of my own code
- [ ] I have commented my code, particularly in hard-to-understand areas
- [ ] I have made corresponding changes to the documentation
- [ ] My changes generate no new warnings
- [ ] Any dependent changes have been merged and published
```

### Review Process
1. **Automated Checks**
   - CI/CD pipeline runs tests
   - Code quality checks pass
   - Security scans complete

2. **Human Review**
   - At least one maintainer review required
   - Address feedback and suggestions
   - Update code based on review

3. **Approval and Merge**
   - All checks pass
   - Approved by maintainer
   - Squash and merge to main

## 🐛 Issue Guidelines

### Bug Reports
Include the following information:

```markdown
## Bug Description
Clear description of what the bug is

## To Reproduce
Steps to reproduce the behavior:
1. Go to '...'
2. Click on '....'
3. Scroll down to '....'
4. See error

## Expected Behavior
What you expected to happen

## Screenshots
If applicable, add screenshots

## Environment
- OS: [e.g. Ubuntu 20.04]
- Browser: [e.g. Chrome 91]
- Docker version: [e.g. 20.10.8]
- GPU: [e.g. NVIDIA RTX 3080]

## Additional Context
Any other context about the problem

## Logs
Relevant log outputs:
```
./opentr.sh logs backend
```
```

### Feature Requests
```markdown
## Feature Description
Clear description of the feature you'd like

## Problem Statement
What problem does this solve?

## Proposed Solution
How should this work?

## Alternatives Considered
Other solutions you've considered

## Additional Context
Any other context, mockups, or examples
```

## 🔒 Security

### Reporting Security Issues
- **DO NOT** create public issues for security vulnerabilities
- Email security concerns to: [security@opentranscribe.com]
- Include detailed description and reproduction steps
- Allow time for fix before public disclosure

### Security Guidelines
- Never commit secrets or API keys
- Use environment variables for sensitive data
- Follow OWASP security practices
- Validate all user inputs
- Use parameterized database queries

## 📖 Documentation Guidelines

### Writing Style
- **Clear and Concise**: Use simple, direct language
- **Examples**: Include code examples and screenshots
- **Structure**: Use headings, lists, and formatting consistently
- **Audience**: Write for developers with varying experience levels

### Documentation Types
1. **README Files**: Quick start and overview
2. **API Documentation**: Endpoint descriptions and examples
3. **Tutorials**: Step-by-step guides
4. **Reference**: Comprehensive technical details

### Documentation Standards
```markdown
# Use proper heading hierarchy

## Level 2 headings for main sections

### Level 3 for subsections

- Use bullet points for lists
- `Use backticks for code`
- **Bold for emphasis**
- *Italic for terms*

```bash
# Code blocks with language specification
./opentr.sh start dev
```
```

## 🎯 Best Practices

### Performance
- **Frontend**: Lazy load components, optimize images, minimize bundle size
- **Backend**: Use async/await, implement caching, optimize database queries
- **AI Processing**: Batch operations, use GPU when available, monitor memory usage

### Accessibility
- Use semantic HTML elements
- Provide alt text for images
- Ensure keyboard navigation works
- Test with screen readers
- Maintain good color contrast

### Internationalization
- Use translation keys instead of hardcoded strings
- Support RTL languages
- Consider cultural differences in UX
- Test with different locales

## 🏆 Recognition

### Contributors
- All contributors are listed in CONTRIBUTORS.md
- Significant contributions are highlighted in release notes
- Regular contributors may be invited as maintainers

### Hall of Fame
- First contribution
- Most helpful community member
- Best documentation improvement
- Most creative feature

## 📞 Getting Help

### Community Support
- **GitHub Discussions**: General questions and discussions
- **Discord**: Real-time chat with the community
- **Stack Overflow**: Use tag `opentranscribe`

### Direct Contact
- **Maintainers**: Tag @maintainers in issues
- **Email**: [contribute@opentranscribe.com]
- **Office Hours**: Virtual office hours every Friday 2-4 PM UTC

### Resources
- [Development Environment Setup Guide](backend/README.md)
- [Frontend Development Guide](frontend/README.md)
- [API Documentation](http://localhost:8080/docs)
- [Architecture Overview](backend/app/README.md)

---

Thank you for contributing to OpenTranscribe! Your efforts help make AI-powered transcription accessible to everyone. 🎉