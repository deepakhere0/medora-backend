from pydantic import BaseModel, ConfigDict


class PatientStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_active:      int
    total_last_month:  int
    growth_percentage: float


class DoctorStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_doctors: int
    on_duty_count: int


class AppointmentStats(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    total_today:     int
    scheduled_count: int
    confirmed_count: int
    completed_count: int
    cancelled_count: int


class WeeklyTrend(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    week_label: str
    count:      int


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    patients:     PatientStats
    doctors:      DoctorStats
    appointments: AppointmentStats
    trend:        list[WeeklyTrend]
