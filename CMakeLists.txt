cmake_minimum_required(VERSION 3.20)
project(omega_native VERSION 2.0.0 LANGUAGES CXX)

# ===== VERSIONING & METADATA =====
set(PRODUCT_VERSION "2.0.0")
set(PRODUCT_NAME "OMEGA Protocol 2.0 Native Backend")
set(COMPANY_NAME "OMEGA Protocol")

# ===== LANGUAGE & STANDARDS =====
set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_FLAGS_RELEASE "/O2 /GL /arch:AVX2 /W4")
set(CMAKE_CXX_FLAGS_DEBUG "/Zi /Od /RTC1 /W4")

# ===== ENSURE x64 BUILD =====
if(CMAKE_GENERATOR_PLATFORM STREQUAL "")
    set(CMAKE_GENERATOR_PLATFORM x64 CACHE STRING "Target platform" FORCE)
endif()

# ===== COMPILER SETTINGS =====
if(MSVC)
    add_compile_options(/permissive- /fp:precise)
    # Disable code analysis warnings for faster builds
    # add_compile_options(/analyze /analyze:stacksize262144)
    
    # Set runtime library to Dynamic
    string(REPLACE "/MT" "/MD" CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE}")
    string(REPLACE "/MTd" "/MDd" CMAKE_CXX_FLAGS_DEBUG "${CMAKE_CXX_FLAGS_DEBUG}")
endif()

# ===== LIBRARY DEFINITION =====
add_library(omega_native SHARED lower.cpp)

# ===== COMPILER DEFINITIONS =====
target_compile_definitions(omega_native PRIVATE 
    UNICODE 
    _UNICODE 
    NOMINMAX
    _CRT_SECURE_NO_WARNINGS
    _WINSOCK_DEPRECATED_NO_WARNINGS
    OEMRESOURCE
    _WIN32_WINNT=0x0A00
)

# ===== LINKING =====
target_link_libraries(omega_native PRIVATE 
    bcrypt.lib
    kernel32.lib
    advapi32.lib
    shell32.lib
    shlwapi.lib
    ntdll.lib
)

# ===== OPTIMIZATION & SECURITY =====
if(MSVC)
    # Set properties for Release builds
    set_target_properties(omega_native PROPERTIES
        MSVC_RUNTIME_LIBRARY "MultiThreadedDLL"
    )
    
    # Link-Time Code Generation for Release
    if(CMAKE_BUILD_TYPE STREQUAL "Release" OR NOT CMAKE_BUILD_TYPE)
        target_compile_options(omega_native PRIVATE /GL)
        target_link_options(omega_native PRIVATE /LTCG /OPT:REF /OPT:ICF)
    endif()
    
    # Security flags for both Release and Debug
    target_link_options(omega_native PRIVATE /DYNAMICBASE /NXCOMPAT /SUBSYSTEM:WINDOWS)
    
    # Enable incremental linking for Debug builds for faster iteration
    if(CMAKE_BUILD_TYPE STREQUAL "Debug")
        target_link_options(omega_native PRIVATE /INCREMENTAL)
    endif()
endif()

# ===== OUTPUT DIRECTORIES - MUST SET BEFORE ADDING TARGETS =====
set_target_properties(omega_native PROPERTIES
    RUNTIME_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/Release"
    RUNTIME_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/Debug"
    RUNTIME_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_BINARY_DIR}/RelWithDebInfo"
    RUNTIME_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_BINARY_DIR}/MinSizeRel"
    
    LIBRARY_OUTPUT_DIRECTORY_RELEASE "${CMAKE_BINARY_DIR}/Release"
    LIBRARY_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/Debug"
    LIBRARY_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_BINARY_DIR}/RelWithDebInfo"
    LIBRARY_OUTPUT_DIRECTORY_MINSIZEREL "${CMAKE_BINARY_DIR}/MinSizeRel"
    
    PDB_OUTPUT_DIRECTORY_DEBUG "${CMAKE_BINARY_DIR}/Debug"
    PDB_OUTPUT_DIRECTORY_RELWITHDEBINFO "${CMAKE_BINARY_DIR}/RelWithDebInfo"
)

# ===== VERSION RESOURCE (Windows Resource) =====
set(VERSION_RC "${CMAKE_CURRENT_BINARY_DIR}/version.rc")
file(WRITE "${VERSION_RC}" "
#include <windows.h>

STRINGTABLE
BEGIN
    1, \"${PRODUCT_VERSION}\"
    2, \"${PRODUCT_NAME}\"
    3, \"${COMPANY_NAME}\"
END

VS_VERSION_INFO VERSIONINFO
FILEVERSION     2,0,0,0
PRODUCTVERSION  2,0,0,0
FILEOS          VOS_NT_WINDOWS32
FILETYPE        VFT_DLL
{
    BLOCK \"StringFileInfo\"
    {
        BLOCK \"040904B0\"
        {
            VALUE \"ProductName\", \"${PRODUCT_NAME}\"
            VALUE \"ProductVersion\", \"${PRODUCT_VERSION}\"
            VALUE \"CompanyName\", \"${COMPANY_NAME}\"
            VALUE \"FileDescription\", \"OMEGA Native Sanitization Backend\"
            VALUE \"FileVersion\", \"${PRODUCT_VERSION}\"
            VALUE \"InternalName\", \"omega_native.dll\"
            VALUE \"OriginalFilename\", \"omega_native.dll\"
            VALUE \"LegalCopyright\", \"Copyright (c) 2026 OMEGA Protocol\"
        }
    }
    BLOCK \"VarFileInfo\"
    {
        VALUE \"Translation\", 0x409, 1200
    }
}
")
target_sources(omega_native PRIVATE ${VERSION_RC})

# ===== INSTALL TARGETS =====
install(TARGETS omega_native 
    RUNTIME DESTINATION bin
    LIBRARY DESTINATION lib
)

# ===== PACKAGE CONFIGURATION =====
set(CMAKE_INSTALL_PREFIX "${CMAKE_BINARY_DIR}/install" CACHE PATH "Installation prefix")
