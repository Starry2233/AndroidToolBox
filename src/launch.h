#pragma once
#ifndef LAUNCH_H
#define LAUNCH_H

#define DEBUG 0

#ifdef _MSC_VER
#define MSVC
#endif

#include <iostream>
#include <stdlib.h>
#include <string>
#include <vector>
#include <stdexcept>
#ifdef _WIN32
#include <windows.h>
#include <sddl.h>
#include <tchar.h>
#else
#include <unistd.h>
#endif

bool IsRunAsAdmin();
void Message();
void ElevatePrivileges();
void RunMainBat();
#ifdef _WIN32
void ClearScreen();
#endif

#endif // LAUNCH_H
