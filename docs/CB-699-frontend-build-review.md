# CB-699: Frontend Build Process Review

**Task**: Review frontend build process
**Story**: CB-692: As a user, I want to...
**Date**: 2026-01-27

---

## Executive Summary

The frontend uses **Next.js 16.1.2** with React 19, TypeScript, and Tailwind CSS v4. The build process is well-structured with a production-optimized Docker multi-stage build producing standalone output. Several areas for improvement have been identified.

---

## Current Build Stack

| Component | Version/Tool |
|-----------|-------------|
| Framework | Next.js 16.1.2 |
| React | 19.2.3 |
| TypeScript | 5.x (strict mode) |
| CSS | Tailwind CSS v4 |
| Testing | Vitest + Playwright |
| Linting | ESLint 9.x |
| Container | Docker (node:20-alpine) |

---

## Build Configuration

### Key Files

- `frontend/next.config.ts` - Next.js configuration (standalone output)
- `frontend/tsconfig.json` - TypeScript with ES2017 target, strict mode
- `frontend/postcss.config.mjs` - Tailwind CSS processing
- `frontend/package.json` - Build scripts and dependencies

### Build Scripts

```json
{
  "dev": "next dev --port 3601",
  "build": "next build",
  "start": "next start --port 3601",
  "lint": "eslint",
  "test": "vitest",
  "test:run": "vitest run",
  "test:coverage": "vitest run --coverage",
  "test:e2e": "playwright test"
}
```

### Port Configuration

| Service | Port |
|---------|------|
| Frontend | 3601 |
| Backend | 8401 |
| ChromaDB | 8501 |

---

## Build Output

- **Output Mode**: Standalone (self-contained for Docker)
- **Output Directory**: `/frontend/.next/`
- **Development Build Size**: ~451 MB
- **Production**: Optimized standalone bundle

---

## Docker Build Strategy

The Dockerfile uses a multi-stage build:

1. **deps stage**: Install npm dependencies
2. **builder stage**: Generate Prisma client, run Next.js build
3. **runner stage**: Production image with standalone output

**Key optimizations**:
- Alpine base for minimal size
- Non-root user (nextjs:1001) for security
- Only production artifacts copied to final image
- Telemetry disabled

---

## Identified Issues

### 1. No Bundle Analysis
- No `@next/bundle-analyzer` configured
- Cannot track bundle size growth over time

### 2. CSS Bundle Size
- `globals.css` has 418 lines of light mode overrides
- Many `!important` flags indicating specificity issues

### 3. Missing Build Optimizations
- No image optimization settings configured
- No compression settings defined
- No caching strategy for static assets

### 4. Testing Performance
- E2E tests run sequentially (1 worker)
- Playwright starts dev server (slower for CI)

### 5. Development Artifacts
- `.next/dev/` directory is 436 MB
- `tsconfig.tsbuildinfo` not in `.gitignore`

---

## Recommendations

### High Priority

1. **Add Bundle Analyzer**
   ```javascript
   // next.config.ts
   import bundleAnalyzer from '@next/bundle-analyzer';

   const withBundleAnalyzer = bundleAnalyzer({
     enabled: process.env.ANALYZE === 'true',
   });
   ```

2. **Add tsconfig.tsbuildinfo to .gitignore**
   - Reduces repository size
   - File is regenerated on build

3. **Configure Image Optimization**
   ```javascript
   // next.config.ts
   images: {
     formats: ['image/avif', 'image/webp'],
     minimumCacheTTL: 60,
   }
   ```

### Medium Priority

4. **Optimize CSS Architecture**
   - Consolidate light mode overrides using CSS custom properties
   - Reduce `!important` usage through better cascade management

5. **Enable Turbopack for Development**
   ```json
   "dev": "next dev --turbo --port 3601"
   ```

6. **Parallel E2E Testing in CI**
   - Increase worker count for CI environments
   - Use production build for E2E tests

### Low Priority

7. **Add Web Vitals Monitoring**
   - Configure performance monitoring
   - Track Core Web Vitals in production

8. **Docker Build Caching**
   - Cache Prisma client generation
   - Optimize layer ordering for better cache hits

---

## Conclusion

The frontend build process is solid and production-ready. The standalone Docker output is well-suited for deployment. The main areas for improvement are:

1. Bundle size monitoring and optimization
2. CSS architecture cleanup
3. Test performance in CI environments

No critical issues were found that would block deployment or development workflows.
