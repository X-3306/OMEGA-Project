// this is compiled into omega_native.dll
#include <windows.h>
#include <bcrypt.h>
#undef WIN32_LEAN_AND_MEAN
#include <ntddstor.h>
#include <strsafe.h>
#include <winioctl.h>

#pragma comment(lib, "bcrypt.lib")

namespace {

constexpr DWORD kChunkSize = 1024 * 1024;

void write_message(wchar_t* buffer, unsigned int capacity, const wchar_t* text) {
    if (!buffer || capacity == 0) {
        return;
    }
    StringCchCopyW(buffer, capacity, text);
}

int last_error_result(wchar_t* buffer, unsigned int capacity, const wchar_t* prefix) {
    DWORD error = GetLastError();
    wchar_t message[256] = L"";
    FormatMessageW(FORMAT_MESSAGE_FROM_SYSTEM | FORMAT_MESSAGE_IGNORE_INSERTS, nullptr, error, 0, message, 256, nullptr);
    wchar_t full[512] = L"";
    StringCchPrintfW(full, 512, L"%s (Win32=%lu: %s)", prefix, error, message);
    write_message(buffer, capacity, full);
    return static_cast<int>(error);
}

bool overwrite_pass(HANDLE file, BYTE* chunk, DWORD chunk_size, LARGE_INTEGER size, bool randomize) {
    LARGE_INTEGER zero{};
    SetFilePointerEx(file, zero, nullptr, FILE_BEGIN);

    LONGLONG remaining = size.QuadPart;
    while (remaining > 0) {
        DWORD to_write = remaining > chunk_size ? chunk_size : static_cast<DWORD>(remaining);
        if (randomize) {
            if (BCryptGenRandom(nullptr, chunk, to_write, BCRYPT_USE_SYSTEM_PREFERRED_RNG) != 0) {
                return false;
            }
        } else {
            SecureZeroMemory(chunk, to_write);
        }

        DWORD written = 0;
        if (!WriteFile(file, chunk, to_write, &written, nullptr) || written != to_write) {
            return false;
        }
        remaining -= written;
    }
    return FlushFileBuffers(file) == TRUE;
}

}  // Author: X-3306

extern "C" __declspec(dllexport) int omega_file_sanitize(
    const wchar_t* path,
    int /*passes*/,
    int dry_run,
    wchar_t* message_buffer,
    unsigned int message_capacity) {
    if (!path || !*path) {
        write_message(message_buffer, message_capacity, L"Invalid path.");
        return ERROR_INVALID_PARAMETER;
    }
    if (dry_run) {
        write_message(message_buffer, message_capacity, L"Dry-run: file sanitize plan accepted.");
        return 0;
    }

    HANDLE file = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, 0, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) {
        return last_error_result(message_buffer, message_capacity, L"CreateFileW failed");
    }

    LARGE_INTEGER size{};
    if (!GetFileSizeEx(file, &size)) {
        CloseHandle(file);
        return last_error_result(message_buffer, message_capacity, L"GetFileSizeEx failed");
    }

    BYTE* chunk = static_cast<BYTE*>(HeapAlloc(GetProcessHeap(), 0, kChunkSize));
    if (!chunk) {
        CloseHandle(file);
        write_message(message_buffer, message_capacity, L"HeapAlloc failed.");
        return ERROR_OUTOFMEMORY;
    }

    int result = 0;
    if (!overwrite_pass(file, chunk, kChunkSize, size, false)) {
        result = last_error_result(message_buffer, message_capacity, L"Zero overwrite pass failed");
        goto cleanup;
    }
    if (!overwrite_pass(file, chunk, kChunkSize, size, true)) {
        result = last_error_result(message_buffer, message_capacity, L"Random overwrite pass failed");
        goto cleanup;
    }

    SetFilePointer(file, 0, nullptr, FILE_BEGIN);
    if (!SetEndOfFile(file)) {
        result = last_error_result(message_buffer, message_capacity, L"SetEndOfFile failed");
        goto cleanup;
    }

cleanup:
    SecureZeroMemory(chunk, kChunkSize);
    HeapFree(GetProcessHeap(), 0, chunk);
    CloseHandle(file);
    if (result != 0) {
        return result;
    }

    if (!DeleteFileW(path)) {
        return last_error_result(message_buffer, message_capacity, L"DeleteFileW failed");
    }

    write_message(message_buffer, message_capacity, L"Native file sanitize completed.");
    return 0;
}

extern "C" __declspec(dllexport) int omega_reinitialize_media(
    unsigned int disk_number,
    unsigned int sanitize_method,
    unsigned int timeout_seconds,
    wchar_t* message_buffer,
    unsigned int message_capacity) {
    wchar_t path[64] = L"";
    StringCchPrintfW(path, 64, L"\\\\.\\PhysicalDrive%u", disk_number);

    HANDLE disk = CreateFileW(path, GENERIC_READ | GENERIC_WRITE, FILE_SHARE_READ | FILE_SHARE_WRITE, nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (disk == INVALID_HANDLE_VALUE) {
        return last_error_result(message_buffer, message_capacity, L"Opening physical drive failed");
    }

    STORAGE_REINITIALIZE_MEDIA request{};
    request.Version = sizeof(STORAGE_REINITIALIZE_MEDIA);
    request.Size = sizeof(STORAGE_REINITIALIZE_MEDIA);
    request.TimeoutInSeconds = timeout_seconds;
    request.SanitizeOption.SanitizeMethod = sanitize_method;
    request.SanitizeOption.DisallowUnrestrictedSanitizeExit = 1;

    DWORD returned = 0;
    BOOL ok = DeviceIoControl(
        disk,
        IOCTL_STORAGE_REINITIALIZE_MEDIA,
        &request,
        sizeof(request),
        nullptr,
        0,
        &returned,
        nullptr);
    CloseHandle(disk);

    if (!ok) {
        return last_error_result(message_buffer, message_capacity, L"IOCTL_STORAGE_REINITIALIZE_MEDIA failed");
    }

    write_message(message_buffer, message_capacity, L"Native disk sanitize request accepted by the driver.");
    return 0;
}
