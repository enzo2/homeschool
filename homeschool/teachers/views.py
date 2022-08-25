import datetime

from denied.authorizers import any_authorized
from denied.decorators import authorize
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import redirect, render, resolve_url

from homeschool.core.schedules import Week
from homeschool.schools.models import SchoolYear

from .forms import ChecklistForm
from .models import Checklist


@authorize(any_authorized)
def checklist(request: HttpRequest, year: int, month: int, day: int) -> HttpResponse:
    """Display a checklist of all the student tasks for a week."""
    today = request.user.get_local_today()
    week_day = datetime.date(year, month, day)
    week = Week(week_day)

    school_year = SchoolYear.get_year_for(request.user, week_day)

    schedules = []
    if school_year:
        schedules = school_year.get_schedules(today, week)
        Checklist.filter_schedules(school_year, schedules)

    context = {"schedules": schedules, "week": week}
    return render(request, "teachers/checklist.html", context)


@authorize(any_authorized)
def edit_checklist(
    request: HttpRequest, year: int, month: int, day: int
) -> HttpResponse:
    """Edit the checklist to allow users to mark courses to exclude."""
    today = request.user.get_local_today()
    week_day = datetime.date(year, month, day)
    week = Week(week_day)

    school_year = SchoolYear.get_year_for(request.user, week_day)
    if school_year is None:
        return HttpResponseNotFound()

    if request.method == "POST":
        form = ChecklistForm(request.POST, school_year=school_year)
        if form.is_valid():
            form.save()
            return redirect(
                resolve_url("teachers:checklist", year=year, month=month, day=day)
            )

    schedules = []
    if school_year:
        schedules = school_year.get_schedules(today, week)

    context = {
        "checklist": Checklist.for_school_year(school_year),
        "schedules": schedules,
        "week": week,
    }
    return render(request, "teachers/edit_checklist.html", context)
