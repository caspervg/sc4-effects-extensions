cmake_minimum_required(VERSION 3.20)

set(CMAKE_TOOLCHAIN_FILE "${CMAKE_CURRENT_SOURCE_DIR}/vendor/vcpkg/scripts/buildsystems/vcpkg.cmake" CACHE STRING "")
set(VCPKG_MANIFEST_MODE ON CACHE BOOL "Enable vcpkg manifest mode")
set(VCPKG_MANIFEST_DIR "${CMAKE_CURRENT_SOURCE_DIR}" CACHE STRING "vcpkg manifest directory")
set(VCPKG_INSTALLED_DIR "${CMAKE_CURRENT_SOURCE_DIR}/vcpkg_installed" CACHE STRING "vcpkg installed directory")
if(NOT DEFINED VCPKG_TARGET_TRIPLET)
    set(VCPKG_TARGET_TRIPLET "x86-windows-static-md" CACHE STRING "Default vcpkg triplet for SimCity 4 DLL builds")
endif()

if(POLICY CMP0091)
    cmake_policy(SET CMP0091 NEW)
endif()

set(SC4_TEMPLATE_VERSION_FALLBACK "0.1.0")
set(SC4_TEMPLATE_PROJECT_VERSION "${SC4_TEMPLATE_VERSION_FALLBACK}")
set(SC4_TEMPLATE_APP_VERSION "${SC4_TEMPLATE_VERSION_FALLBACK}")

find_package(Git QUIET)
if(GIT_FOUND AND EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/.git")
    execute_process(
        COMMAND "${GIT_EXECUTABLE}" describe --tags --abbrev=0
        WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
        OUTPUT_VARIABLE SC4_TEMPLATE_GIT_TAG
        OUTPUT_STRIP_TRAILING_WHITESPACE
        ERROR_QUIET
    )

    if(SC4_TEMPLATE_GIT_TAG)
        set(SC4_TEMPLATE_APP_VERSION "${SC4_TEMPLATE_GIT_TAG}")

        execute_process(
            COMMAND "${GIT_EXECUTABLE}" describe --tags --dirty --always
            WORKING_DIRECTORY "${CMAKE_CURRENT_SOURCE_DIR}"
            OUTPUT_VARIABLE SC4_TEMPLATE_GIT_DESCRIBE
            OUTPUT_STRIP_TRAILING_WHITESPACE
            ERROR_QUIET
        )

        if(SC4_TEMPLATE_GIT_DESCRIBE)
            set(SC4_TEMPLATE_APP_VERSION "${SC4_TEMPLATE_GIT_DESCRIBE}")
        endif()

        string(REGEX REPLACE "^v" "" SC4_TEMPLATE_PROJECT_VERSION "${SC4_TEMPLATE_GIT_TAG}")
    endif()
endif()

project(SC4TemplateDll VERSION ${SC4_TEMPLATE_PROJECT_VERSION} LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 23)
set(CMAKE_CXX_STANDARD_REQUIRED ON)

option(SC4_ENABLE_PLUGIN_DEPLOYMENT "Copy the built DLL into Documents/SimCity 4/Plugins after each build" ON)

if(WIN32)
    add_definitions(-DWIN32 -D_WINDOWS -DUNICODE -D_UNICODE)
endif()

if(MSVC)
    add_compile_options(/W4 /permissive-)
    add_compile_definitions(_CRT_SECURE_NO_WARNINGS)
    set(CMAKE_CXX_FLAGS_RELEASE "${CMAKE_CXX_FLAGS_RELEASE} /Zi")
    set(CMAKE_SHARED_LINKER_FLAGS_RELEASE "${CMAKE_SHARED_LINKER_FLAGS_RELEASE} /DEBUG /OPT:REF /OPT:ICF")
endif()

find_package(spdlog CONFIG REQUIRED)
find_package(wil CONFIG REQUIRED)

add_subdirectory(src/dll)
