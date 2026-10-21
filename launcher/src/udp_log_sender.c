/* SPDX-License-Identifier: MIT */
/* Bounded IPv4 UDP breadcrumb sender. No DNS, network configuration, or kexec. */
#define _POSIX_C_SOURCE 200809L
#include <arpa/inet.h>
#include <errno.h>
#include <poll.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/socket.h>
#include <time.h>
#include <unistd.h>

static int token(const char *s, size_t maximum)
{
    size_t n = strlen(s);
    if (!n || n > maximum) return 0;
    for (; *s; ++s)
        if (!( (*s >= 'a' && *s <= 'z') || (*s >= 'A' && *s <= 'Z') ||
               (*s >= '0' && *s <= '9') || strchr("_.:-", *s))) return 0;
    return 1;
}

static long long milliseconds(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts)) return -1;
    return (long long)ts.tv_sec * 1000 + ts.tv_nsec / 1000000;
}

int main(int argc, char **argv)
{
    struct sockaddr_in local = {0}, peer = {0};
    struct pollfd pfd;
    char message[1024], expected[256], reply[256], *end;
    unsigned long port, sequence;
    int fd, n, attempt, result = 4;

    if (argc != 10) {
        fprintf(stderr, "usage: %s SOURCE_IP RECEIVER_IP PORT EXPERIMENT SOURCE_BOOT ACTUAL_BOOT SEQUENCE EVENT DETAIL\n", argv[0]);
        return 2;
    }
    local.sin_family = peer.sin_family = AF_INET;
    if (inet_pton(AF_INET, argv[1], &local.sin_addr) != 1 ||
        inet_pton(AF_INET, argv[2], &peer.sin_addr) != 1) return 2;
    errno = 0;
    port = strtoul(argv[3], &end, 10);
    if (errno || *end || !port || port > 65535) return 2;
    errno = 0;
    sequence = strtoul(argv[7], &end, 10);
    if (errno || *end || !sequence || sequence > 1000000) return 2;
    if (!token(argv[4], 80) || !token(argv[5], 36) || !token(argv[6], 36) ||
        !token(argv[8], 64) || !token(argv[9], 128)) return 2;
    peer.sin_port = htons((unsigned short)port);
    n = snprintf(message, sizeof(message),
        "{\"protocol\":\"percept-stage-v1\",\"experiment\":\"%s\","
        "\"source_boot\":\"%s\",\"actual_boot\":\"%s\",\"sequence\":%lu,"
        "\"event\":\"%s\",\"detail\":\"%s\"}",
        argv[4], argv[5], argv[6], sequence, argv[8], argv[9]);
    if (n < 0 || (size_t)n >= sizeof(message)) return 2;
    snprintf(expected, sizeof(expected), "ACK %lu %s %s", sequence, argv[4], argv[6]);
    fd = socket(AF_INET, SOCK_DGRAM | SOCK_NONBLOCK, 0);
    if (fd < 0) return 3;
    /* Connected UDP accepts replies only from the selected receiver IP/port. */
    if (bind(fd, (struct sockaddr *)&local, sizeof(local)) ||
        connect(fd, (struct sockaddr *)&peer, sizeof(peer))) {
        close(fd);
        return 3;
    }
    pfd.fd = fd;
    pfd.events = POLLIN;
    for (attempt = 0; attempt < 3; ++attempt) {
        long long now = milliseconds(), deadline;
        if (now < 0) break;
        deadline = now + 250;
        if (send(fd, message, (size_t)n, 0) != n) continue;
        while ((now = milliseconds()) >= 0 && now < deadline) {
            int ready = poll(&pfd, 1, (int)(deadline - now));
            ssize_t got;
            if (ready < 0 && errno == EINTR) continue;
            if (ready <= 0) break;
            got = recv(fd, reply, sizeof(reply) - 1, 0);
            if (got < 0) break;
            reply[got] = '\0';
            if (!strcmp(reply, expected)) {
                result = 0;
                goto done;
            }
        }
    }
done:
    close(fd);
    return result;
}
