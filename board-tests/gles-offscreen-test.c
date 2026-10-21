/* Headless GLES2 render proof for the Percept's Vivante GC7000 (etnaviv).
 *
 * Opens the DRM render node through a GBM device, makes a surfaceless GLES2
 * context, draws a shaded triangle into an FBO and verifies the pixels read
 * back against the expected geometry and colour. It refuses to pass on a
 * software renderer (llvmpipe/softpipe/swrast) and repeats the draw to look
 * for hangs. No display connector is needed.
 *
 *   cc -O2 -o gles-offscreen-test gles-offscreen-test.c -lEGL -lGLESv2 -lgbm
 *   ./gles-offscreen-test [/dev/dri/renderD128] [frames]
 */
#define _GNU_SOURCE
#include <EGL/egl.h>
#include <EGL/eglext.h>
#include <GLES2/gl2.h>
#include <fcntl.h>
#include <gbm.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#define W 256
#define H 256

static const char *vs_src =
    "attribute vec2 pos; attribute vec3 col; varying vec3 vcol;\n"
    "void main(){ vcol = col; gl_Position = vec4(pos, 0.0, 1.0); }\n";
static const char *fs_src =
    "precision mediump float; varying vec3 vcol;\n"
    "void main(){ gl_FragColor = vec4(vcol, 1.0); }\n";

static GLuint compile(GLenum type, const char *src)
{
    GLuint s = glCreateShader(type);
    glShaderSource(s, 1, &src, NULL);
    glCompileShader(s);
    GLint ok = 0;
    glGetShaderiv(s, GL_COMPILE_STATUS, &ok);
    if (!ok) {
        char log[512];
        glGetShaderInfoLog(s, sizeof log, NULL, log);
        fprintf(stderr, "shader compile failed: %s\n", log);
        exit(2);
    }
    return s;
}

static int near(int a, int b, int tol) { return abs(a - b) <= tol; }

int main(int argc, char **argv)
{
    const char *node = argc > 1 ? argv[1] : "/dev/dri/renderD128";
    int frames = argc > 2 ? atoi(argv[2]) : 200;

    int fd = open(node, O_RDWR | O_CLOEXEC);
    if (fd < 0) { perror(node); return 2; }
    struct gbm_device *gbm = gbm_create_device(fd);
    if (!gbm) { fprintf(stderr, "gbm_create_device failed\n"); return 2; }

    PFNEGLGETPLATFORMDISPLAYEXTPROC get_display =
        (PFNEGLGETPLATFORMDISPLAYEXTPROC)eglGetProcAddress("eglGetPlatformDisplayEXT");
    if (!get_display) { fprintf(stderr, "no eglGetPlatformDisplayEXT\n"); return 2; }
    EGLDisplay dpy = get_display(EGL_PLATFORM_GBM_KHR, gbm, NULL);
    EGLint major, minor;
    if (dpy == EGL_NO_DISPLAY || !eglInitialize(dpy, &major, &minor)) {
        fprintf(stderr, "eglInitialize failed (0x%x)\n", eglGetError());
        return 2;
    }
    eglBindAPI(EGL_OPENGL_ES_API);
    EGLint cfg_attr[] = { EGL_RENDERABLE_TYPE, EGL_OPENGL_ES2_BIT,
                          EGL_SURFACE_TYPE, EGL_DONT_CARE, EGL_NONE };
    EGLConfig cfg; EGLint n = 0;
    if (!eglChooseConfig(dpy, cfg_attr, &cfg, 1, &n) || n < 1) {
        fprintf(stderr, "no EGL config\n"); return 2;
    }
    EGLint ctx_attr[] = { EGL_CONTEXT_CLIENT_VERSION, 2, EGL_NONE };
    EGLContext ctx = eglCreateContext(dpy, cfg, EGL_NO_CONTEXT, ctx_attr);
    if (ctx == EGL_NO_CONTEXT || !eglMakeCurrent(dpy, EGL_NO_SURFACE, EGL_NO_SURFACE, ctx)) {
        fprintf(stderr, "context failed (0x%x)\n", eglGetError());
        return 2;
    }

    const char *renderer = (const char *)glGetString(GL_RENDERER);
    const char *vendor = (const char *)glGetString(GL_VENDOR);
    printf("node=%s EGL=%d.%d\nGL_VENDOR=%s\nGL_RENDERER=%s\nGL_VERSION=%s\n",
           node, major, minor, vendor, renderer, glGetString(GL_VERSION));
    if (!renderer || strcasestr(renderer, "llvmpipe") || strcasestr(renderer, "softpipe") ||
        strcasestr(renderer, "swrast") || !strcasestr(renderer, "Vivante")) {
        fprintf(stderr, "FAIL: not the Vivante hardware renderer\n");
        return 3;
    }

    GLuint tex, fbo;
    glGenTextures(1, &tex);
    glBindTexture(GL_TEXTURE_2D, tex);
    glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, W, H, 0, GL_RGBA, GL_UNSIGNED_BYTE, NULL);
    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST);
    glGenFramebuffers(1, &fbo);
    glBindFramebuffer(GL_FRAMEBUFFER, fbo);
    glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0, GL_TEXTURE_2D, tex, 0);
    if (glCheckFramebufferStatus(GL_FRAMEBUFFER) != GL_FRAMEBUFFER_COMPLETE) {
        fprintf(stderr, "FBO incomplete\n"); return 2;
    }

    GLuint prog = glCreateProgram();
    glAttachShader(prog, compile(GL_VERTEX_SHADER, vs_src));
    glAttachShader(prog, compile(GL_FRAGMENT_SHADER, fs_src));
    glBindAttribLocation(prog, 0, "pos");
    glBindAttribLocation(prog, 1, "col");
    glLinkProgram(prog);
    GLint ok = 0;
    glGetProgramiv(prog, GL_LINK_STATUS, &ok);
    if (!ok) { fprintf(stderr, "link failed\n"); return 2; }
    glUseProgram(prog);

    /* Triangle covering the lower-left half; red, green, blue corners. */
    static const GLfloat verts[] = {
        -1.f, -1.f,  1.f, 0.f, 0.f,
         1.f, -1.f,  0.f, 1.f, 0.f,
        -1.f,  1.f,  0.f, 0.f, 1.f,
    };
    glVertexAttribPointer(0, 2, GL_FLOAT, GL_FALSE, 5 * sizeof(GLfloat), verts);
    glVertexAttribPointer(1, 3, GL_FLOAT, GL_FALSE, 5 * sizeof(GLfloat), verts + 2);
    glEnableVertexAttribArray(0);
    glEnableVertexAttribArray(1);
    glViewport(0, 0, W, H);

    static unsigned char px[W * H * 4];
    int bad_frames = 0;
    for (int f = 0; f < frames; f++) {
        glClearColor(0.f, 0.f, 0.f, 1.f);
        glClear(GL_COLOR_BUFFER_BIT);
        glDrawArrays(GL_TRIANGLES, 0, 3);
        glReadPixels(0, 0, W, H, GL_RGBA, GL_UNSIGNED_BYTE, px);
        GLenum err = glGetError();
        if (err != GL_NO_ERROR) { fprintf(stderr, "GL error 0x%x at frame %d\n", err, f); return 4; }

        /* Outside the triangle (upper-right) must be the clear colour. */
        const unsigned char *out = &px[((H - 4) * W + (W - 4)) * 4];
        /* Near the red corner (lower-left) must be strongly red. */
        const unsigned char *red = &px[(4 * W + 4) * 4];
        /* Near the centroid all three channels contribute roughly equally. */
        const unsigned char *mid = &px[((H / 3) * W + (W / 3)) * 4];
        int good = near(out[0], 0, 2) && near(out[1], 0, 2) && near(out[2], 0, 2) &&
                   red[0] > 230 && red[1] < 25 && red[2] < 25 &&
                   near(mid[0], 85, 20) && near(mid[1], 85, 20) && near(mid[2], 85, 20);
        if (!good) {
            bad_frames++;
            if (bad_frames == 1)
                fprintf(stderr, "frame %d wrong: out=%u,%u,%u red=%u,%u,%u mid=%u,%u,%u\n", f,
                        out[0], out[1], out[2], red[0], red[1], red[2], mid[0], mid[1], mid[2]);
        }
    }

    unsigned long sum = 0;
    for (int i = 0; i < W * H * 4; i++) sum = sum * 131 + px[i];
    FILE *ppm = fopen("gles-offscreen.ppm", "wb");
    if (ppm) {
        fprintf(ppm, "P6\n%d %d\n255\n", W, H);
        for (int y = H - 1; y >= 0; y--)
            for (int x = 0; x < W; x++)
                fwrite(&px[(y * W + x) * 4], 1, 3, ppm);
        fclose(ppm);
    }
    printf("frames=%d bad_frames=%d pixel_checksum=%lx wrote=gles-offscreen.ppm\n",
           frames, bad_frames, sum);
    printf(bad_frames ? "RESULT: FAIL\n" : "RESULT: PASS (hardware render verified)\n");
    return bad_frames ? 1 : 0;
}
