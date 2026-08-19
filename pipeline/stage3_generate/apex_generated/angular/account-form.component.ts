import { Component, OnInit, inject } from '@angular/core';
import { CommonModule } from '@angular/common';
import {
  FormBuilder,
  FormGroup,
  ReactiveFormsModule,
  AbstractControl,
  AsyncValidatorFn,
  ValidationErrors,
  ValidatorFn,
} from '@angular/forms';
import { Observable, of, timer } from 'rxjs';
import { map, switchMap, catchError, first } from 'rxjs/operators';
import { AccountService } from './account.service';

/**
 * Validator mirroring APEX "Valid Tag Characters" (EXPRESSION):
 *   not regexp_like( :P3_TAGS, '[:;#\/\\\?\&]' )
 * Tags may not contain: : ; # / \ ? &
 */
export function tagCharactersValidator(): ValidatorFn {
  const blacklist = /[:;#\/\\?&]/;
  return (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    if (value === null || value === undefined || value === '') {
      return null;
    }
    return blacklist.test(value)
      ? { invalidTagCharacters: 'Tags may not contain the following characters: : ; \\ / ? &' }
      : null;
  };
}

/**
 * Validator mirroring APEX "must start with http" (EXPRESSION):
 *   substr(:PX, 1, 4) = 'http'
 * Only validates when a value is present (APEX EXPRESSION validations
 * only fire when the item has a value / is submitted).
 */
export function startsWithHttpValidator(): ValidatorFn {
  return (control: AbstractControl): ValidationErrors | null => {
    const value = control.value;
    if (value === null || value === undefined || value === '') {
      return null;
    }
    return String(value).substr(0, 4) === 'http'
      ? null
      : { mustStartWithHttp: 'Please provide a URL that begins with, "http".' };
  };
}

/**
 * Async validator mirroring APEX "P3_CUSTOMER_NAME not duplicated" (NOT_EXISTS):
 *   select null from eba_sales_customers
 *   where (:P3_ID is null or :P3_ID != id)
 *     and upper(customer_name) = upper(:P3_CUSTOMER_NAME)
 *
 * The provided getId callback supplies the current record id (P3_ID) so the
 * record being edited is excluded from the duplicate check.
 */
export function uniqueCustomerNameValidator(
  accountService: AccountService,
  getId: () => number | null | undefined
): AsyncValidatorFn {
  return (control: AbstractControl): Observable<ValidationErrors | null> => {
    const value = control.value;
    if (value === null || value === undefined || value === '') {
      return of(null);
    }
    return timer(300).pipe(
      switchMap(() =>
        accountService.isCustomerNameTaken(value, getId() ?? null).pipe(
          map((taken) =>
            taken
              ? { customerNameExists: 'An account with that name already exists.' }
              : null
          ),
          catchError(() => of(null))
        )
      ),
      first()
    );
  };
}

@Component({
  selector: 'app-account-form',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule],
  templateUrl: './account-form.component.html',
})
export class AccountFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private accountService = inject(AccountService);

  form!: FormGroup;

  ngOnInit(): void {
    this.form = this.fb.group({
      id: [null],
      customerName: [
        null,
        {
          validators: [],
          asyncValidators: [
            uniqueCustomerNameValidator(
              this.accountService,
              () => this.form?.get('id')?.value
            ),
          ],
          updateOn: 'blur',
        },
      ],
      tags: [null, [tagCharactersValidator()]],
      customerWebSite: [null, [startsWithHttpValidator()]],
      customerLinkedin: [null, [startsWithHttpValidator()]],
      customerFacebook: [null, [startsWithHttpValidator()]],
      customerTwitter: [null, [startsWithHttpValidator()]],
    });
  }

  get f() {
    return this.form.controls;
  }

  patch(model: Partial<{
    id: number | null;
    customerName: string;
    tags: string;
    customerWebSite: string;
    customerLinkedin: string;
    customerFacebook: string;
    customerTwitter: string;
  }>): void {
    this.form.patchValue(model);
  }

  submit(): void {
    if (this.form.invalid) {
      this.form.markAllAsTouched();
      return;
    }
    this.accountService.save(this.form.value).subscribe();
  }
}