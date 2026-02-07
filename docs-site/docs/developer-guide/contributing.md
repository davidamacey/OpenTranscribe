---
sidebar_position: 2
---

# Contributing

We welcome contributions to OpenTranscribe!

## Getting Started

1. Fork the repository
2. Clone your fork
3. Create a feature branch
4. Make your changes
5. Test thoroughly
6. Submit a pull request

## Development Setup

```bash
git clone https://github.com/YOUR_USERNAME/OpenTranscribe.git
cd OpenTranscribe
./opentr.sh start dev
```

## Code Guidelines

- Follow existing code style
- Add tests for new features (see [Testing Guide](./testing.md))
- Update documentation
- Keep commits focused

## Testing Requirements

All contributions should include appropriate tests:

- **Backend changes**: Add unit tests in `backend/tests/`
- **Frontend changes**: Add E2E tests in `backend/tests/e2e/`
- **API changes**: Update API endpoint tests

Run tests before submitting:

```bash
# Unit tests
pytest backend/tests/ --ignore=backend/tests/e2e/ -v

# E2E tests (requires dev environment)
pytest backend/tests/e2e/ -v
```

## Reporting Issues

Use GitHub Issues to report:
- Bugs
- Feature requests
- Documentation improvements

## Next Steps

- [Architecture](./architecture.md)
- [Testing Guide](./testing.md)
- [GitHub Repository](https://github.com/davidamacey/OpenTranscribe)
